# Adjudicatorinstruktion — beskrivningsstudie

Adjudikeringen sker **före retrieval**. Granskaren får inte se lexical/fallback-resultat, ranker eller tidigare modellbedömningar.

## Underlag som får visas

Visa endast:

- `case_id`;
- `stream` (`occupation` eller `skill`);
- `description_redacted`;
- språk om det behövs för tolkning.

Visa inte deltagar-ID, retrievalresultat eller information som kan styra granskaren mot en viss kandidat.

## Uppgift

Bedöm om beskrivningen kan mappas till aktuell kanonisk taxonomiidentitet.

Använd exakt en av statusarna:

- `mapped`: exakt en defensibel kanonisk identitet;
- `ambiguous`: minst två defensibla kanoniska identiteter;
- `clarification-needed`: texten är för vag för en säker mappning men en enkel förtydligande fråga skulle kunna lösa det;
- `unmappable`: beskrivningen är begriplig och inom domänen men någon lämplig kanonisk identitet kan inte försvaras;
- `out-of-scope`: texten beskriver inte ett yrke respektive en kompetens som studien kan bedöma.

Tvinga aldrig fram en enda identitet för att göra benchmarken enklare.

## Acceptabla mål

För varje acceptabel identitet lagras:

```json
{
  "canonical_id": "...",
  "in_frozen_demand_envelope": true
}
```

Fältet `in_frozen_demand_envelope` har stream-specifik betydelse. För `skill` bedöms medlemskap per mål mot den frusna 316-kompetensers P80-envelopen; ett tvetydigt skill-fall kan därför ha mål både innanför och utanför. För `occupation` är capability-universumet alla **2 105 aktiva v31 `occupation-name`**. Varje giltigt aktivt occupation-mål ska därför ha `in_frozen_demand_envelope: true`; P80/non-P80 noteras separat som efterfrågestratum och får inte avgöra om yrket är ett giltigt mål.

## Evidensstandard

- Använd den styrande taxonomikällan för v31 och produktens definierade identitetsyta.
- Skapa inga nya synonymer eller sammanslagna koncept under adjudikeringen.
- Jobbtitel/context får inte förväxlas med occupation-name-identitet när occupation-streamen kräver occupation-name.
- För skill-streamen får ett out-of-P80-mål inte ersättas av närmaste P80-kompetens.
- För occupation-streamen får ett aktivt v31 `occupation-name` utanför P80 inte märkas som out-of-envelope eller ersättas av ett P80-yrke.
- Om texten saknar avgörande information: välj `clarification-needed`, inte en gissning.

## När ett fall får driva större modellkomplexitet

Ett exploratory pilotfall kan ha en granskare. Ett fall som senare används som positiv evidens för att den frusna stream-specifika fallback-kandidaten är semantiskt otillräcklig bör få starkare oberoende adjudikering enligt den preregistrerade proceduren — före någon ny modell jämförs mot fallet.

Retrieval får köras först när adjudikationsfilen är fryst och dess SHA-256 finns i manifestet.
