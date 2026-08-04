package com.quietcue.app.data

import com.quietcue.app.domain.ProfileDefaults
import org.junit.Assert.assertEquals
import org.junit.Test

class ProfileJsonCodecTest {
    @Test
    fun `profile collection survives persistence round trip`() {
        val profiles = ProfileDefaults.all() + ProfileDefaults.newCustom()

        val restored = ProfileJsonCodec.decode(ProfileJsonCodec.encode(profiles))

        assertEquals(profiles, restored)
    }

    @Test
    fun `blank input decodes to an empty collection`() {
        assertEquals(emptyList<Any>(), ProfileJsonCodec.decode(""))
    }
}
