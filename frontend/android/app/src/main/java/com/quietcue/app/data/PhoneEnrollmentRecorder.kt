package com.quietcue.app.data

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.quietcue.app.domain.AcousticFingerprint
import com.quietcue.app.domain.CapturedFingerprint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class PhoneEnrollmentRecorder {
    @SuppressLint("MissingPermission")
    suspend fun recordFingerprint(durationMs: Int = 2_000): CapturedFingerprint = withContext(Dispatchers.IO) {
        require(durationMs in 500..5_000)
        val minimumBuffer = AudioRecord.getMinBufferSize(
            AcousticFingerprint.SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        check(minimumBuffer > 0) { "This phone cannot record 16 kHz mono audio" }
        val recorder = AudioRecord.Builder()
            .setAudioSource(MediaRecorder.AudioSource.MIC)
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(AcousticFingerprint.SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                    .build(),
            )
            .setBufferSizeInBytes(maxOf(minimumBuffer, 4_096))
            .build()
        check(recorder.state == AudioRecord.STATE_INITIALIZED) { "Phone microphone could not be initialized" }

        val targetSamples = AcousticFingerprint.SAMPLE_RATE * durationMs / 1_000
        val samples = ShortArray(targetSamples)
        var offset = 0
        try {
            recorder.startRecording()
            while (offset < samples.size) {
                val read = recorder.read(samples, offset, minOf(2_048, samples.size - offset), AudioRecord.READ_BLOCKING)
                check(read > 0) { "Phone microphone stopped while recording" }
                offset += read
            }
        } finally {
            if (recorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) recorder.stop()
            recorder.release()
        }
        AcousticFingerprint.fromPcm16(samples)
    }
}
