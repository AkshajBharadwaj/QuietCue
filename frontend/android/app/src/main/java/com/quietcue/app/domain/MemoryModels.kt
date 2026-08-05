package com.quietcue.app.domain

data class UserIdentity(
    val displayName: String,
    val pronunciation: String = "",
    val aliases: List<String> = emptyList(),
    val recognitionPhrases: List<String> = emptyList(),
    val updatedAtEpochMs: Long = System.currentTimeMillis(),
)

data class PersonMemory(
    val id: String,
    val name: String,
    val relationship: String = "",
    val pronunciation: String = "",
    val aliases: List<String> = emptyList(),
    val notes: String = "",
    val updatedAtEpochMs: Long = System.currentTimeMillis(),
)

data class ContextMemory(
    val id: String,
    val title: String,
    val details: String,
    val updatedAtEpochMs: Long = System.currentTimeMillis(),
)

data class MemoryBank(
    val identity: UserIdentity? = null,
    val people: List<PersonMemory> = emptyList(),
    val contexts: List<ContextMemory> = emptyList(),
) {
    val isEmpty: Boolean get() = identity == null && people.isEmpty() && contexts.isEmpty()
}

object MemoryBankValidator {
    const val MAX_PEOPLE = 50
    const val MAX_CONTEXTS = 50

    fun validate(bank: MemoryBank): List<String> = buildList {
        bank.identity?.let { identity ->
            if (identity.displayName.isBlank() || identity.displayName.length > 60) {
                add("Your name must be between 1 and 60 characters.")
            }
            if (identity.pronunciation.length > 80) add("Pronunciation must be 80 characters or fewer.")
            validateTextList(identity.aliases, 10, 60, "identity aliases")?.let(::add)
            validateTextList(identity.recognitionPhrases, 5, 100, "recognition samples")?.let(::add)
        }
        if (bank.people.size > MAX_PEOPLE) add("The memory bank supports up to $MAX_PEOPLE people.")
        if (bank.contexts.size > MAX_CONTEXTS) add("The memory bank supports up to $MAX_CONTEXTS context entries.")
        if (bank.people.map { it.id }.distinct().size != bank.people.size) add("People must have unique IDs.")
        if (bank.contexts.map { it.id }.distinct().size != bank.contexts.size) add("Context entries must have unique IDs.")
        bank.people.forEach { person ->
            if (person.id.isBlank() || person.id.length > 80) add("Each person needs a valid ID.")
            if (person.name.isBlank() || person.name.length > 60) add("Each person's name must be 1 to 60 characters.")
            if (person.relationship.length > 80) add("Relationships must be 80 characters or fewer.")
            if (person.pronunciation.length > 80) add("Pronunciations must be 80 characters or fewer.")
            if (person.notes.length > 280) add("Person notes must be 280 characters or fewer.")
            validateTextList(person.aliases, 10, 60, "person aliases")?.let(::add)
        }
        bank.contexts.forEach { context ->
            if (context.id.isBlank() || context.id.length > 80) add("Each context entry needs a valid ID.")
            if (context.title.isBlank() || context.title.length > 80) add("Context titles must be 1 to 80 characters.")
            if (context.details.isBlank() || context.details.length > 500) {
                add("Context details must be 1 to 500 characters.")
            }
        }
    }.distinct()

    private fun validateTextList(
        values: List<String>,
        maximumItems: Int,
        maximumLength: Int,
        label: String,
    ): String? = if (
        values.size > maximumItems ||
        values.any { it.isBlank() || it.length > maximumLength } ||
        values.distinctBy { it.lowercase() }.size != values.size
    ) {
        "Invalid $label."
    } else null
}
