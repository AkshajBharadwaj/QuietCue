package com.quietcue.app.phone.speech

import ai.onnxruntime.OnnxJavaType
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.TensorInfo
import android.content.Context
import com.quietcue.app.domain.SpeechModel
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.nio.IntBuffer

/** Greedy decoder for the explicit-cache Qualcomm AI Hub Whisper ONNX export. */
class WhisperOnnxTranscriber(
    context: Context,
    val model: SpeechModel,
) : PhoneTranscriber {
    private val appContext = context.applicationContext
    private val environment = OrtEnvironment.getEnvironment()
    private val features = WhisperFeatureExtractor()
    private val vocabulary: WhisperVocabulary
    private val encoder: OrtSession
    private val decoder: OrtSession
    private val decoderLayers: List<Int>
    private val maxDecodeLength: Int

    init {
        val materialized = materializeAssets()
        vocabulary = appContext.assets.open("${model.assetDirectory}/$VOCABULARY_ASSET")
            .bufferedReader()
            .use { WhisperVocabulary.fromJson(it.readText()) }
        val options = OrtSession.SessionOptions().apply {
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        encoder = environment.createSession(File(materialized, ENCODER_ASSET).absolutePath, options)
        decoder = environment.createSession(File(materialized, DECODER_ASSET).absolutePath, options)
        validateEncoderContract()
        decoderLayers = decoder.inputNames.mapNotNull { name ->
            SELF_KEY_INPUT.matchEntire(name)?.groupValues?.get(1)?.toInt()
        }.sorted()
        require(decoderLayers.isNotEmpty() && decoderLayers == decoderLayers.indices.toList()) {
            "Whisper decoder self-attention cache layers are incomplete"
        }
        decoderLayers.forEach { layer ->
            require("v_cache_self_${layer}_in" in decoder.inputNames) { "Missing self value cache $layer" }
            require("k_cache_self_${layer}_out" in decoder.outputNames) { "Missing self key output $layer" }
            require("v_cache_self_${layer}_out" in decoder.outputNames) { "Missing self value output $layer" }
            require("k_cache_cross_$layer" in decoder.inputNames) { "Missing cross key cache $layer" }
            require("v_cache_cross_$layer" in decoder.inputNames) { "Missing cross value cache $layer" }
            require("k_cache_cross_$layer" in encoder.outputNames) { "Encoder cross key output $layer is missing" }
            require("v_cache_cross_$layer" in encoder.outputNames) { "Encoder cross value output $layer is missing" }
        }
        require(REQUIRED_DECODER_INPUTS.all(decoder.inputNames::contains)) {
            "Whisper decoder does not match the Qualcomm AI Hub explicit-cache contract"
        }
        require("logits" in decoder.outputNames) { "Whisper decoder output 'logits' is missing" }
        requireFloat32Inputs(encoder)
        requireFloat32Inputs(decoder, exempt = setOf("input_ids", "position_ids"))
        requireInt32(decoder, "input_ids")
        requireInt32(decoder, "position_ids")
        decoder.outputNames.forEach { name ->
            require(outputInfo(decoder, name).type == OnnxJavaType.FLOAT) {
                "Whisper ONNX output $name must be float32"
            }
        }
        encoder.outputNames.forEach { name ->
            require(outputInfo(encoder, name).type == OnnxJavaType.FLOAT) {
                "Whisper ONNX output $name must be float32"
            }
        }
        val logitsShape = outputInfo(decoder, "logits").shape
        require(
            logitsShape.size == 4 && logitsShape[0] == 1L && logitsShape[1] == vocabulary.size.toLong() &&
                logitsShape[2] == 1L && logitsShape[3] == 1L
        ) { "Whisper logits must be float32[1,vocabulary,1,1]" }
        val attentionShape = inputInfo(decoder, "attention_mask").shape
        require(attentionShape.size == 4 && attentionShape.last() > 1) {
            "Whisper attention mask must have a fixed decode length"
        }
        maxDecodeLength = attentionShape.last().toInt()
    }

    @Synchronized
    override fun transcribe(pcm: ByteArray): String? {
        val mel = features.pcm16ToLogMel(pcm)
        val melTensor = OnnxTensor.createTensor(
            environment,
            mel,
            longArrayOf(1, WhisperFeatureExtractor.MEL_BANDS.toLong(), WhisperFeatureExtractor.MEL_FRAMES.toLong()),
        )
        var encoderResult: OrtSession.Result? = null
        var decoderResult: OrtSession.Result? = null
        val initialSelfCaches = mutableMapOf<String, OnnxTensor>()
        val mutableInputs = mutableListOf<OnnxTensor>()
        try {
            encoderResult = encoder.run(mapOf(ENCODER_INPUT to melTensor))
            val encoderOutputs = encoder.outputNames.associateWith { name ->
                encoderResult.get(name).orElseThrow { IllegalStateException("Encoder output $name is missing") }
                    as OnnxTensor
            }
            decoderLayers.forEach { layer ->
                listOf("k_cache_self_${layer}_in", "v_cache_self_${layer}_in").forEach { name ->
                    initialSelfCaches[name] = zeroFloatTensor(inputInfo(decoder, name).shape)
                }
            }

            val tokenBuffer = directIntBuffer(1)
            val positionBuffer = directIntBuffer(1)
            val maskBuffer = directFloatBuffer(maxDecodeLength).apply {
                repeat(maxDecodeLength) { put(-100.0f) }
                flip()
            }
            val tokenTensor = OnnxTensor.createTensor(environment, tokenBuffer, longArrayOf(1, 1))
            val positionTensor = OnnxTensor.createTensor(environment, positionBuffer, longArrayOf(1))
            val maskTensor = OnnxTensor.createTensor(
                environment,
                maskBuffer,
                inputInfo(decoder, "attention_mask").shape,
            )
            mutableInputs += listOf(tokenTensor, positionTensor, maskTensor)

            val outputTokens = mutableListOf(vocabulary.startOfTranscript)
            var currentToken = vocabulary.startOfTranscript
            for (position in 0 until maxDecodeLength - 1) {
                tokenBuffer.put(0, currentToken)
                positionBuffer.put(0, position)
                maskBuffer.put(maxDecodeLength - position - 1, 0.0f)
                val inputs = mutableMapOf<String, OnnxTensor>(
                    "input_ids" to tokenTensor,
                    "position_ids" to positionTensor,
                    "attention_mask" to maskTensor,
                )
                decoderLayers.forEach { layer ->
                    inputs["k_cache_self_${layer}_in"] = selfCache(
                        decoderResult,
                        initialSelfCaches,
                        "k_cache_self_${layer}_in",
                    )
                    inputs["v_cache_self_${layer}_in"] = selfCache(
                        decoderResult,
                        initialSelfCaches,
                        "v_cache_self_${layer}_in",
                    )
                    inputs["k_cache_cross_$layer"] = requireNotNull(encoderOutputs["k_cache_cross_$layer"])
                    inputs["v_cache_cross_$layer"] = requireNotNull(encoderOutputs["v_cache_cross_$layer"])
                }

                val previousResult = decoderResult
                val nextResult = decoder.run(inputs)
                if (previousResult == null) {
                    initialSelfCaches.values.forEach(OnnxTensor::close)
                    initialSelfCaches.clear()
                } else {
                    previousResult.close()
                }
                decoderResult = nextResult
                val greedyToken = argmax(
                    nextResult.get("logits").orElseThrow { IllegalStateException("Decoder logits are missing") }
                        as OnnxTensor,
                )
                val nextToken = selectWhisperToken(position, greedyToken, vocabulary) ?: break
                outputTokens += nextToken
                currentToken = nextToken
            }
            return vocabulary.decode(outputTokens).ifBlank { null }
        } finally {
            decoderResult?.close()
            initialSelfCaches.values.forEach(OnnxTensor::close)
            mutableInputs.forEach(OnnxTensor::close)
            encoderResult?.close()
            melTensor.close()
        }
    }

    override fun close() {
        decoder.close()
        encoder.close()
    }

    private fun validateEncoderContract() {
        require(encoder.inputNames == setOf(ENCODER_INPUT)) {
            "Whisper encoder must expose only '$ENCODER_INPUT'"
        }
        val shape = inputInfo(encoder, ENCODER_INPUT).shape
        require(shape.contentEquals(longArrayOf(1, 80, 3_000))) {
            "Whisper encoder input must be float32[1,80,3000]"
        }
    }

    private fun requireFloat32Inputs(session: OrtSession, exempt: Set<String> = emptySet()) {
        session.inputNames.filterNot(exempt::contains).forEach { name ->
            require(inputInfo(session, name).type == OnnxJavaType.FLOAT) {
                "Whisper ONNX input $name must be float32; export without float16 I/O for ORT Android"
            }
        }
    }

    private fun requireInt32(session: OrtSession, name: String) {
        require(inputInfo(session, name).type == OnnxJavaType.INT32) {
            "Whisper ONNX input $name must be int32"
        }
    }

    private fun selfCache(
        result: OrtSession.Result?,
        initial: Map<String, OnnxTensor>,
        inputName: String,
    ): OnnxTensor {
        if (result == null) return requireNotNull(initial[inputName])
        val outputName = inputName.removeSuffix("_in") + "_out"
        return result.get(outputName).orElseThrow {
            IllegalStateException("Decoder output $outputName is missing")
        } as OnnxTensor
    }

    private fun argmax(tensor: OnnxTensor): Int {
        val values = tensor.floatBuffer
        values.rewind()
        require(values.hasRemaining()) { "Whisper decoder returned empty logits" }
        var bestIndex = 0
        var bestValue = Float.NEGATIVE_INFINITY
        var index = 0
        while (values.hasRemaining()) {
            val value = values.get()
            if (value > bestValue) {
                bestValue = value
                bestIndex = index
            }
            index += 1
        }
        return bestIndex
    }

    private fun zeroFloatTensor(shape: LongArray): OnnxTensor {
        require(shape.all { it > 0 }) { "Whisper cache shapes must be static" }
        val count = shape.fold(1L, Long::times)
        require(count <= Int.MAX_VALUE) { "Whisper cache tensor is too large" }
        return OnnxTensor.createTensor(environment, directFloatBuffer(count.toInt()), shape)
    }

    private fun materializeAssets(): File {
        val assetDirectory = model.assetDirectory
        val assetNames = appContext.assets.list(assetDirectory).orEmpty().toList()
        require(REQUIRED_ASSETS.all(assetNames::contains)) {
            "${model.displayName} assets are missing; run scripts/prepare_whisper_assets.py"
        }
        val directory = File(appContext.filesDir, "whisper-${model.name.lowercase()}").apply { mkdirs() }
        assetNames.filterNot { it == VOCABULARY_ASSET }.forEach { assetName ->
            copyAssetIfChanged("$assetDirectory/$assetName", File(directory, assetName))
        }
        return directory
    }

    private fun copyAssetIfChanged(assetName: String, destination: File) {
        val expectedSize = appContext.assets.openFd(assetName).use { it.length }
        if (destination.isFile && destination.length() == expectedSize) return
        val temporary = File(destination.parentFile, "${destination.name}.tmp")
        appContext.assets.open(assetName).use { input ->
            temporary.outputStream().use(input::copyTo)
        }
        if (destination.exists()) check(destination.delete()) { "Could not replace ${destination.name}" }
        check(temporary.renameTo(destination)) { "Could not install model asset $assetName" }
    }

    private fun inputInfo(session: OrtSession, name: String): TensorInfo =
        session.inputInfo.getValue(name).info as? TensorInfo
            ?: error("Whisper input $name is not a tensor")

    private fun outputInfo(session: OrtSession, name: String): TensorInfo =
        session.outputInfo.getValue(name).info as? TensorInfo
            ?: error("Whisper output $name is not a tensor")

    private fun directFloatBuffer(size: Int): FloatBuffer = ByteBuffer
        .allocateDirect(size * Float.SIZE_BYTES)
        .order(ByteOrder.nativeOrder())
        .asFloatBuffer()

    private fun directIntBuffer(size: Int): IntBuffer = ByteBuffer
        .allocateDirect(size * Int.SIZE_BYTES)
        .order(ByteOrder.nativeOrder())
        .asIntBuffer()

    companion object {
        private const val ENCODER_ASSET = "encoder.onnx"
        private const val DECODER_ASSET = "decoder.onnx"
        private const val VOCABULARY_ASSET = "vocabulary.json"
        private const val ENCODER_INPUT = "input_features"
        private val REQUIRED_ASSETS = setOf(ENCODER_ASSET, DECODER_ASSET, VOCABULARY_ASSET)
        private val REQUIRED_DECODER_INPUTS = setOf("input_ids", "attention_mask", "position_ids")
        private val SELF_KEY_INPUT = Regex("k_cache_self_(\\d+)_in")
    }
}

internal fun selectWhisperToken(
    position: Int,
    greedyToken: Int,
    vocabulary: WhisperVocabulary,
): Int? {
    val shouldStop = greedyToken == vocabulary.endOfText || greedyToken == vocabulary.noSpeech
    if ((position == 0 || position >= 3) && shouldStop) return null
    return when (position) {
        0 -> vocabulary.english
        1 -> vocabulary.transcribe
        2 -> vocabulary.noTimestamps
        else -> greedyToken
    }
}
