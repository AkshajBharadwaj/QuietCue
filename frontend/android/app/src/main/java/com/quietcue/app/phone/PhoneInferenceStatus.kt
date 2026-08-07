package com.quietcue.app.phone

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class PhoneInferenceServerState(
    val running: Boolean = false,
    val modelReady: Boolean = false,
    val clientConnected: Boolean = false,
    val port: Int = PhoneInferenceServer.DEFAULT_PORT,
    val provider: String = "loading",
    val lastEvent: String? = null,
    val inferenceMs: Double? = null,
    val speechModelLoaded: Boolean = false,
    val speechListening: Boolean = false,
    val speechPending: Boolean = false,
    val speechInferenceMs: Double? = null,
    val speechError: String? = null,
    val error: String? = null,
)

object PhoneInferenceStatus {
    private val mutable = MutableStateFlow(PhoneInferenceServerState())
    val state: StateFlow<PhoneInferenceServerState> = mutable.asStateFlow()

    fun update(transform: (PhoneInferenceServerState) -> PhoneInferenceServerState) {
        mutable.value = transform(mutable.value)
    }
}
