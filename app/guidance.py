# SPDX-License-Identifier: AGPL-3.0-only
"""Participant-facing guidance for the unchanged decision tree."""

CHECKS = {
    "en": {
        "result": (
            "Finding",
            "Does the extraction correctly report what was studied, measured and found in abstract {side}?",
            "Compare the exposure, outcome and finding with the highlighted text, including the direction.",
            "Check the exposure or intervention, the outcome and the finding against the highlighted text. The finding shown is chosen because it concerns the same exposure and outcome as the other abstract: if it is a secondary finding, say so in the optional note before submitting. If the direction is reversed, or an intended result is presented as observed, choose “No” and, at the question “What is wrong?” that appears below, choose “Wrong direction” or “A planned result is presented as observed”.",
            "If the abstract reports a lower level but the extraction says higher, choose “No” and, at the question “What is wrong?”, “Wrong direction”. If the abstract reports a significant association or difference and the extraction says there is none, choose “No” and, at the same question, “Not supported by the abstract”.",
        ),
        "groups": (
            "People and groups",
            "Does the extraction correctly identify the people, groups and subgroup for this finding in abstract {side}?",
            "Check who the finding applies to, including any stated subgroup.",
            "Check the study groups and the subgroup for this result, not just the whole study population. “Study population” and “Comparison group” always appear: the “Name used in the study” is data to check, not a label. If the “Comparison group” says there is no comparison group, check that the finding really does not compare two groups. Check “People included in the analysis” too. Do not infer that all participants belong to a subgroup.",
            "If a finding concerns women with a particular condition but the extraction says all women, choose “No” and, at the question “What is wrong?”, “Wrong group or time point”.",
        ),
        "sample_size": (
            "Sample size",
            "Does the extraction give the correct sample sizes, for the whole study and for each group, in abstract {side}?",
            "Check each number and the group it refers to: a number given in the abstract but missing here is an error.",
            "Distinguish the whole study from a group or subgroup, and people from studies or events. “Whole study” is filled only if the abstract states the total number of participants. Do not derive an unreported size from the groups or from a total.",
            "If 80 is the total for two groups but the extraction assigns 80 to each group, choose “No” and, at the question “What is wrong?”, “A value or wording differs from the abstract”.",
        ),
        "comparison": (
            "Comparison",
            "Does the extraction correctly describe what was compared in abstract {side}?",
            "Check whether it is a comparison between groups, a change from baseline or an association.",
            "Check “Compared with”, “Starting time” and “Time of measurement”. A change within one group is not a difference between treatments; an association does not require two treatment groups.",
            "If glucose fell within both treatment groups, that alone does not show that one treatment lowered it more.",
        ),
        "analysis": (
            "Study and analysis",
            "Does the extraction correctly describe the study and analysis in abstract {side}?",
            "Check the aims, design, method and adjustment, including any separate subgroup analyses.",
            "The stated aims also help you see whether the finding you are checking is the main one or a secondary one: a secondary finding extracted correctly is not an error. Adjusting for a variable is different from analysing separate subgroups. Check the analysis method against the abstract too.",
            "Using BMI as an adjustment variable does not mean the study analysed normal-weight and overweight groups separately.",
        ),
        "significance": (
            "Statistical evidence",
            "Does the extraction match the statistical evidence reported in abstract {side}?",
            "Check the p-value, interval or wording and what it refers to.",
            "Check both numbers and the authors’ wording. An interaction p-value is not automatically the p-value for the main comparison. Do not infer significance from a direction or from an absent p-value. “Stated as a hypothesis” describes how the authors present the finding: “Yes” if they state it tentatively (for example “may”, “suggests”, “could”), “No” if they state it as observed. It is not about significance or the study’s starting hypothesis. If it does not match the abstract’s wording, in the “Statistical evidence” row choose “No” and, at the question “What is wrong?”, “A value or wording differs from the abstract”. If the extraction says “Significant” but the authors do not state it, choose “No” and, at the same question, “Not supported by the abstract”.",
            "A p-value for a time trend must not be presented as evidence for a difference between two treatments.",
        ),
        "context": (
            "Context",
            "Does the extraction correctly report the dose, duration, place and biological material for abstract {side}?",
            "Check the dose, duration, place and biological material. A field showing “Not extracted” is correct only when the abstract does not give that information.",
            "Check each value shown against the abstract. Biological material means, for example, serum or plasma; it is not the sample size.",
            "If the abstract says plasma but the extraction says serum, choose “No” and, at the question “What is wrong?”, “A value or wording differs from the abstract”.",
        ),
    },
    "it": {
        "result": (
            "Risultato",
            "L’estrazione riporta correttamente che cosa è stato studiato, misurato e osservato nell’abstract {side}?",
            "Confronta esposizione, esito e risultato con il testo evidenziato, compresa la direzione.",
            "Controlla esposizione o intervento, esito misurato e risultato, confrontandoli con il testo evidenziato. Il risultato mostrato è scelto perché riguarda la stessa esposizione e lo stesso esito dell’altro abstract: se è un risultato secondario, scrivilo nella nota facoltativa prima dell’invio. Se la direzione è invertita, o un risultato atteso è presentato come già osservato, scegli «No» e, alla domanda «Qual è il problema?» che compare sotto, scegli «Direzione del risultato invertita» o «Un risultato atteso è presentato come osservato».",
            "Se l’abstract riporta un livello più basso e l’estrazione dice più alto, scegli «No» e, alla domanda «Qual è il problema?», «Direzione del risultato invertita». Se l’abstract riporta un’associazione o una differenza significativa e l’estrazione dice che non c’è, scegli «No» e, alla stessa domanda, «L’abstract non lo sostiene».",
        ),
        "groups": (
            "Persone e gruppi",
            "L’estrazione indica correttamente le persone, i gruppi e il sottogruppo di questo risultato nell’abstract {side}?",
            "Controlla a chi si riferisce il risultato, compresi eventuali sottogruppi.",
            "Controlla i gruppi dello studio e il sottogruppo di questo risultato, non solo la popolazione generale. «Popolazione in studio» e «Gruppo di confronto» compaiono sempre: il «Nome usato nello studio» è un dato da controllare, non un’etichetta. Se il «Gruppo di confronto» indica che non c’è un gruppo di confronto, controlla che il risultato davvero non confronti due gruppi. Controlla anche «Persone incluse nell’analisi». Non supporre che tutti i partecipanti appartengano a un sottogruppo.",
            "Se il risultato riguarda donne con una certa condizione e l’estrazione dice tutte le donne, scegli «No» e, alla domanda «Qual è il problema?», «Gruppo o momento della misura errati».",
        ),
        "sample_size": (
            "Numerosità",
            "L’estrazione riporta le numerosità corrette, per l’intero studio e per ciascun gruppo, nell’abstract {side}?",
            "Controlla ogni numero e il gruppo a cui si riferisce: un numero presente nell’abstract ma assente qui è un errore.",
            "Distingui l’intero studio da un gruppo o sottogruppo e le persone dagli studi o dagli eventi. «Intero studio» si compila solo se l’abstract scrive il numero totale dei partecipanti. Non ricavare una numerosità non riportata dai gruppi o dal totale.",
            "Se 80 è il totale dei due gruppi ma l’estrazione attribuisce 80 a ciascun gruppo, scegli «No» e, alla domanda «Qual è il problema?», «Un valore o una formulazione è diverso dall’abstract».",
        ),
        "comparison": (
            "Confronto",
            "L’estrazione descrive correttamente che cosa viene confrontato nell’abstract {side}?",
            "Controlla se è un confronto tra gruppi, una variazione dal valore iniziale o un’associazione.",
            "Controlla «Confrontato con», «Momento di partenza» e «Momento della misura». Una variazione nello stesso gruppo non è una differenza tra trattamenti; un’associazione non richiede due gruppi di trattamento.",
            "Se la glicemia diminuisce in entrambi i gruppi, questo da solo non dimostra che un trattamento la riduca più dell’altro.",
        ),
        "analysis": (
            "Studio e analisi",
            "L’estrazione descrive correttamente lo studio e l’analisi nell’abstract {side}?",
            "Controlla obiettivi, disegno, metodo e aggiustamenti, comprese le analisi separate dei sottogruppi.",
            "Gli obiettivi dichiarati ti aiutano anche a capire se il risultato che stai controllando è quello principale o uno secondario: un risultato secondario estratto bene non è un errore. Considerare una variabile nell’aggiustamento non equivale ad analizzare sottogruppi separati. Controlla nel testo anche il metodo dell’analisi.",
            "Usare il BMI come variabile di aggiustamento non significa aver analizzato separatamente persone normopeso e sovrappeso.",
        ),
        "significance": (
            "Evidenza statistica",
            "L’estrazione corrisponde all’evidenza statistica riportata nell’abstract {side}?",
            "Controlla p-value, intervallo o parole degli autori e a cosa si riferiscono.",
            "Controlla sia i numeri sia le parole degli autori. Un p-value per l’interazione non è automaticamente quello del confronto principale. Non dedurre la significatività dalla direzione o dall’assenza del p-value. «Formulato come ipotesi» dice come gli autori presentano il risultato: «Sì» se lo esprimono con cautela (per esempio «may», «suggests», «could»), «No» se lo affermano come osservato. Non riguarda la significatività né l’ipotesi di partenza dello studio. Se non corrisponde alle parole dell’abstract, nella riga «Evidenza statistica» scegli «No» e, alla domanda «Qual è il problema?», «Un valore o una formulazione è diverso dall’abstract». Se l’estrazione indica «Significativo» ma gli autori non lo dichiarano, scegli «No» e, alla stessa domanda, «L’abstract non lo sostiene».",
            "Un p-value relativo all’andamento nel tempo non va presentato come prova di una differenza tra due trattamenti.",
        ),
        "context": (
            "Contesto",
            "L’estrazione riporta correttamente dose, durata, luogo e materiale biologico dell’abstract {side}?",
            "Controlla dose, durata, luogo e materiale biologico. Un campo «Non estratto» è corretto solo se l’abstract non riporta quell’informazione.",
            "Verifica nel testo ogni valore mostrato. Il materiale biologico è, per esempio, siero o plasma: non è il numero dei partecipanti.",
            "Se l’abstract parla di plasma e l’estrazione indica siero, scegli «No» e, alla domanda «Qual è il problema?», «Un valore o una formulazione è diverso dall’abstract».",
        ),
    },
}

HOW = {
    "en": {
        "q2_exposure": "Check what was studied, not just whether the names look alike.",
        "q2_outcome": "The outcome is the variable measured, for example LDL cholesterol, not the finding. Check what was measured and how it was defined.",
        "q2_comparison": "Check the reference, measurement and time point; convertible units can agree.",
        "q1_relevance": "An error is still an error: here you only decide whether, in the extracted data, it changes the finding or the comparison.",
        "q3": "Compare direction and conclusions, not statistical significance alone.",
        "q4": "Distinguish non-confirmation, opposite directions and size alone.",
        "q5": "Use a relevant difference described by the abstracts, not outside knowledge.",
        "q5_factor": "Choose the difference best supported by the texts.",
        "q2_primary": "Keep all your reasons; select the one that determines your decision.",
    },
    "it": {
        "q2_exposure": "Controlla che cosa è stato studiato, non solo se i nomi si somigliano.",
        "q2_outcome": "L’esito è la variabile misurata, per esempio il colesterolo LDL, non il risultato ottenuto. Controlla che cosa è stato misurato e come è stato definito.",
        "q2_comparison": "Controlla riferimento, misura e momento; unità convertibili possono concordare.",
        "q1_relevance": "Un errore resta un errore: qui decidi solo se, nei dati estratti, cambia il risultato o il confronto.",
        "q3": "Confronta direzione e conclusioni, non la sola significatività statistica.",
        "q4": "Distingui mancata conferma, direzioni opposte e sola differenza di entità.",
        "q5": "Usa una differenza pertinente descritta negli abstract, non conoscenze esterne.",
        "q5_factor": "Scegli la differenza meglio sostenuta dai testi.",
        "q2_primary": "Conserva tutti i motivi; scegli quello decisivo per il tuo giudizio.",
    },
}

EXAMPLES = {
    "en": {
        "q2_exposure": "A particular medicine and its class are comparable only if that comparison makes sense for these findings. The same substance measured in serum in one study and in plasma in the other is the same exposure: if the difference in material matters and the findings are opposite, report it in the last question.",
        "q2_outcome": "Blood glucose and body weight are different outcomes even if both studies concern diabetes.",
        "q2_comparison": "A value at week 12 and a change from baseline are not automatically the same comparison.",
        "q1_relevance": "A missing number is an error that usually leaves the finding unchanged; an invented comparison group changes it.",
        "q3": "Two reductions can agree despite different sizes. If one study states that an effect was not confirmed, choose “No”: the next question asks how they differ.",
        "q4": "An increase versus no confirmed effect is different from an increase versus a decrease.",
        "q5": "Different doses described in the abstracts may explain opposite findings; an unmentioned diet is not an available explanation.",
        "q5_factor": "Choose “Statistical analysis or adjustment” for different adjustment methods, and “Sample size, when it helps explain the finding” for a relevant numerical difference.",
        "q2_primary": "If both exposure and outcome differ, retain both checks and select the decisive reason here.",
    },
    "it": {
        "q2_exposure": "Un farmaco e la sua classe sono confrontabili solo se il confronto ha senso per questi risultati. La stessa sostanza misurata nel siero in uno studio e nel plasma nell’altro è la stessa esposizione: se la differenza di materiale conta e i risultati sono opposti, indicala nell’ultima domanda.",
        "q2_outcome": "Glicemia e peso corporeo sono esiti diversi, anche se entrambi gli studi riguardano il diabete.",
        "q2_comparison": "Un valore alla settimana 12 e una variazione dal valore iniziale non sono automaticamente lo stesso confronto.",
        "q1_relevance": "Un numero mancante è un errore che di solito lascia invariato il risultato; un gruppo di confronto inventato lo cambia.",
        "q3": "Due riduzioni possono concordare anche se diverse per entità. Se uno studio dichiara di non aver confermato l’effetto, scegli «No»: la domanda successiva chiede in cosa differiscono.",
        "q4": "Un aumento rispetto a un effetto non confermato è diverso da un aumento rispetto a una diminuzione.",
        "q5": "Dosi diverse descritte negli abstract possono spiegare risultati opposti; una dieta non menzionata non è una spiegazione disponibile.",
        "q5_factor": "Scegli «Analisi statistica o aggiustamenti» per aggiustamenti diversi e «Numerosità, se aiuta a spiegare il risultato» per una differenza numerica pertinente.",
        "q2_primary": "Se differiscono sia l’esposizione sia l’esito, conserva entrambe le risposte e scegli qui il motivo decisivo.",
    },
}


def guidance_copy(lang):
    from .presentation import FIELD_LABELS

    return {
        "field_labels": FIELD_LABELS[lang],
        "keywords": KEYWORDS[lang],
        "missing_help": "«Non estratto» significa che il sistema ha lasciato il campo vuoto; «Non riportato» significa che il sistema dice che l’abstract non lo riporta. Entrambe le indicazioni possono essere sbagliate: controlla tutto l’abstract."
        if lang == "it"
        else "“Not extracted” means the system left the field empty; “Not reported” means the system says the abstract does not give it. Either can be wrong: check the whole abstract.",
        # The standard line under every row check.
        "missing_line": "Se un dato manca qui, cercalo in tutto l’abstract: se c’è, scegli «No»."
        if lang == "it"
        else "If a detail is missing here, look for it in the whole abstract: if it is there, choose “No”.",
        "checks": {
            key: dict(zip(("name", "question", "how", "help", "example"), values, strict=True))
            for key, values in CHECKS[lang].items()
        },
        "how": HOW[lang],
        "examples": EXAMPLES[lang],
        # The general rule, read before the first row check.
        "q1_frame": "Per ognuna delle 7 righe, confronta l’estrazione con l’abstract. Scegli «No» se un campo è sbagliato, impreciso o incompleto, oppure se è «Non estratto» o «Non riportato» ma l’abstract riporta quell’informazione. Scegli «Sì» solo se tutti i campi della riga corrispondono all’abstract."
        if lang == "it"
        else "For each of the 7 rows, compare the extraction with the abstract. Choose “No” if a field is wrong, imprecise or incomplete, or if it shows “Not extracted” or “Not reported” but the abstract gives that information. Choose “Yes” only if every field in the row matches the abstract.",
        "help_label": "Aiuto per questa domanda" if lang == "it" else "Help for this question",
        "help_close": "Chiudi" if lang == "it" else "Close",
        "example_label": "Esempio" if lang == "it" else "Example",
        "answer_guide": "Scegli «Sì» se corrisponde al testo, «No» se trovi un errore. Se il testo non basta per giudicare, scegli «Non posso stabilirlo»."
        if lang == "it"
        else "Choose “Yes” if it matches the text, “No” if you find an error. If the text is insufficient to judge, choose “Cannot tell”.",
        "review_block": "Rivedi" if lang == "it" else "Review",
        "completed_block": "{side}: {count} di 7 controlli fatti"
        if lang == "it"
        else "{side}: {count} of 7 checks done",
    }


# Short presentation labels; the questions and answer codes stay unchanged.
KEYWORDS = {
    "it": {
        "result": "Risultato",
        "groups": "Persone e gruppi",
        "sample_size": "Numerosità",
        "comparison": "Confronto",
        "analysis": "Studio e analisi",
        "significance": "Evidenza statistica",
        "context": "Contesto",
        "relevance": "Effetto sul risultato",
        "exposure": "Stessa esposizione",
        "outcome": "Stesso esito",
        "measures": "Misure e confronti",
        "primary": "Motivo principale",
        "q3": "Stesso risultato",
        "q4": "Tipo di differenza",
        "q5": "Spiegazione negli abstract",
        "factor": "Differenza indicata",
    },
    "en": {
        "result": "Finding",
        "groups": "People and groups",
        "sample_size": "Sample size",
        "comparison": "Comparison",
        "analysis": "Study and analysis",
        "significance": "Statistical evidence",
        "context": "Context",
        "relevance": "Effect on the finding",
        "exposure": "Same exposure",
        "outcome": "Same outcome",
        "measures": "Measures and comparisons",
        "primary": "Main reason",
        "q3": "Same finding",
        "q4": "How they differ",
        "q5": "Explanation in the abstracts",
        "factor": "Difference chosen",
    },
}
