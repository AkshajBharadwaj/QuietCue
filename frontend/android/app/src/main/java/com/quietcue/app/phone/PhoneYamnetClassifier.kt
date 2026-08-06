package com.quietcue.app.phone

import ai.onnxruntime.OnnxJavaType
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import java.io.Closeable
import java.io.File
import java.nio.ByteOrder
import kotlin.math.exp

data class PhoneSoundPrediction(val label: String, val confidence: Double)

interface PhoneSoundClassifier : Closeable {
    val provider: String
    fun classify(pcm: ByteArray, topK: Int = 10): List<PhoneSoundPrediction>
}

class PhoneYamnetClassifier(context: Context) : PhoneSoundClassifier {
    private val appContext = context.applicationContext
    private val environment = OrtEnvironment.getEnvironment()
    private val features = YamnetFeatureExtractor()
    private val labels = appContext.assets.open(LABELS_ASSET).bufferedReader().use { reader ->
        reader.readLines().map(String::trim).filter(String::isNotEmpty)
    }
    private val session: OrtSession
    private val inputName: String

    override val provider: String = "onnx_cpu"

    init {
        require(labels.size == OUTPUT_CLASSES) { "Expected $OUTPUT_CLASSES AudioSet labels" }
        val model = materializeModel()
        val options = OrtSession.SessionOptions().apply {
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        session = environment.createSession(model.absolutePath, options)
        inputName = session.inputNames.single()
    }

    override fun classify(pcm: ByteArray, topK: Int): List<PhoneSoundPrediction> {
        require(topK > 0) { "topK must be positive" }
        val input = features.pcm16ToQuantizedPatch(pcm)
        OnnxTensor.createTensor(
            environment,
            input,
            longArrayOf(1, 1, YamnetFeatureExtractor.PATCH_FRAMES.toLong(), YamnetFeatureExtractor.MEL_BANDS.toLong()),
            OnnxJavaType.UINT8,
        ).use { tensor ->
            session.run(mapOf(inputName to tensor)).use { result ->
                val output = result[0] as OnnxTensor
                val values = output.byteBuffer.duplicate().order(ByteOrder.nativeOrder())
                values.rewind()
                require(values.remaining() == OUTPUT_CLASSES) {
                    "Expected $OUTPUT_CLASSES scores, received ${values.remaining()}"
                }
                return List(OUTPUT_CLASSES) { index ->
                    val quantized = values.get().toInt() and 0xff
                    val logits = (quantized - OUTPUT_ZERO_POINT) * OUTPUT_SCALE
                    PhoneSoundPrediction(labels[index], 1.0 / (1.0 + exp(-logits)))
                }.sortedByDescending(PhoneSoundPrediction::confidence).take(topK)
            }
        }
    }

    override fun close() {
        session.close()
    }

    private fun materializeModel(): File {
        val directory = File(appContext.filesDir, "yamnet-w8a8").apply { mkdirs() }
        val model = File(directory, MODEL_ASSET)
        val data = File(directory, DATA_ASSET)
        copyAssetIfChanged(MODEL_ASSET, model)
        copyAssetIfChanged(DATA_ASSET, data)
        return model
    }

    private fun copyAssetIfChanged(assetName: String, destination: File) {
        val expectedSize = appContext.assets.openFd(assetName).use { it.length }
        if (destination.isFile && destination.length() == expectedSize) return
        val temporary = File(destination.parentFile, "${destination.name}.tmp")
        appContext.assets.open(assetName).use { input ->
            temporary.outputStream().use { output ->
                input.copyTo(output)
            }
        }
        check(temporary.renameTo(destination)) { "Could not install model asset $assetName" }
    }

    companion object {
        private const val MODEL_ASSET = "yamnet.onnx"
        private const val DATA_ASSET = "yamnet.data"
        private const val LABELS_ASSET = "labels.txt"
        private const val OUTPUT_CLASSES = 521
        private const val OUTPUT_SCALE = 0.7587278485298157
        private const val OUTPUT_ZERO_POINT = 190
    }
}
