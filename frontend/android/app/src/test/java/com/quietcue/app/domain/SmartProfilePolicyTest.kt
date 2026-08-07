package com.quietcue.app.domain

import org.junit.Assert.assertEquals
import org.junit.Test

class SmartProfilePolicyTest {
    private val work = SmartPlace(
        id = "work",
        name = "Work",
        latitude = 37.0,
        longitude = -122.0,
        profileId = "profile-work",
    )
    private val profiles = setOf("profile-home", "profile-work")

    @Test
    fun `arrival suggests the mapped profile by default`() {
        val decision = SmartProfilePolicy.decide(
            place = work,
            transition = PlaceTransition.ENTER,
            state = SmartProfileState(),
            activeProfileId = "profile-home",
            availableProfileIds = profiles,
            nowEpochMs = 1_000L,
        )

        assertEquals(SmartProfileDecisionType.SUGGEST, decision.type)
        assertEquals("profile-work", decision.targetProfileId)
    }

    @Test
    fun `explicit automatic mode activates on arrival`() {
        val decision = SmartProfilePolicy.decide(
            place = work.copy(autoApply = true),
            transition = PlaceTransition.ENTER,
            state = SmartProfileState(),
            activeProfileId = "profile-home",
            availableProfileIds = profiles,
            nowEpochMs = 1_000L,
        )

        assertEquals(SmartProfileDecisionType.ACTIVATE, decision.type)
    }

    @Test
    fun `recent manual selection prevents automatic activation`() {
        val now = 10_000L
        val decision = SmartProfilePolicy.decide(
            place = work.copy(autoApply = true),
            transition = PlaceTransition.ENTER,
            state = SmartProfileState(manualOverrideUntilEpochMs = now + 60_000L),
            activeProfileId = "profile-home",
            availableProfileIds = profiles,
            nowEpochMs = now,
        )

        assertEquals(SmartProfileDecisionType.SUGGEST, decision.type)
    }

    @Test
    fun `automatic place returns to previous profile on exit`() {
        val decision = SmartProfilePolicy.decide(
            place = work.copy(autoApply = true),
            transition = PlaceTransition.EXIT,
            state = SmartProfileState(
                activePlaceId = work.id,
                returnProfileId = "profile-home",
            ),
            activeProfileId = "profile-work",
            availableProfileIds = profiles,
            nowEpochMs = 20_000L,
        )

        assertEquals(SmartProfileDecisionType.ACTIVATE, decision.type)
        assertEquals("profile-home", decision.targetProfileId)
    }

    @Test
    fun `duplicate transition inside cooldown is ignored`() {
        val now = 500_000L
        val decision = SmartProfilePolicy.decide(
            place = work,
            transition = PlaceTransition.ENTER,
            state = SmartProfileState(
                lastTransitionKey = "work:ENTER",
                lastTransitionAtEpochMs = now - 1_000L,
            ),
            activeProfileId = "profile-home",
            availableProfileIds = profiles,
            nowEpochMs = now,
        )

        assertEquals(SmartProfileDecisionType.IGNORE, decision.type)
    }
}
