package com.quietcue.app.data

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import java.util.Locale
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine

class OnDeviceNameRecognizer(private val context: Context) {
    suspend fun recognize(): String = suspendCancellableCoroutine { continuation ->
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            !SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
        ) {
            continuation.resumeWithException(
                IllegalStateException("On-device speech recognition is unavailable. Add pronunciation aliases manually."),
            )
            return@suspendCancellableCoroutine
        }

        val recognizer = SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
        var finished = false

        fun complete(result: Result<String>) {
            if (finished) return
            finished = true
            recognizer.destroy()
            if (continuation.isActive) {
                result.onSuccess { continuation.resume(it) }
                    .onFailure { continuation.resumeWithException(it) }
            }
        }

        recognizer.setRecognitionListener(
            object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) = Unit
                override fun onBeginningOfSpeech() = Unit
                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() = Unit
                override fun onPartialResults(partialResults: Bundle?) = Unit
                override fun onEvent(eventType: Int, params: Bundle?) = Unit

                override fun onError(error: Int) {
                    complete(Result.failure(IllegalStateException(errorMessage(error))))
                }

                override fun onResults(results: Bundle?) {
                    val text = results
                        ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        ?.firstOrNull(String::isNotBlank)
                    if (text == null) complete(Result.failure(IllegalStateException("No speech was recognized.")))
                    else complete(Result.success(text.trim()))
                }
            },
        )
        continuation.invokeOnCancellation {
            if (!finished) {
                finished = true
                recognizer.cancel()
                recognizer.destroy()
            }
        }
        recognizer.startListening(
            Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toLanguageTag())
                putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            },
        )
    }

    private fun errorMessage(error: Int): String = when (error) {
        SpeechRecognizer.ERROR_AUDIO -> "The microphone could not capture the sample."
        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Microphone permission is required."
        SpeechRecognizer.ERROR_NO_MATCH -> "The name was not recognized. Try speaking clearly and closer to the phone."
        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "The speech recognizer is busy. Try again."
        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "No speech was heard."
        SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED ->
            "This language is not supported by the phone's on-device recognizer. Add pronunciation aliases manually."
        SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE ->
            "The phone's offline speech pack is not installed. Install it in phone settings or add aliases manually."
        else -> "On-device recognition failed (code $error)."
    }
}
