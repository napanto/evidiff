# SPDX-License-Identifier: AGPL-3.0-only
"""Versioned instrument: human wording and authoritative answer-path validation.

The browser submits choices, never a category.  ``parse_answer`` derives the
legacy label/factor, retaining field diagnostics separately from the pair label.
"""

import json

INSTRUMENT_VERSION = "2.0"
FIELDS = ("result", "groups", "sample_size", "comparison", "analysis", "significance", "context")
# The order in which the checks are shown: what the result sentence
# states, then the methods in reading order. Codes and validation use FIELDS unchanged.
DISPLAY_ORDER = (
    "result",
    "comparison",
    "significance",
    "analysis",
    "groups",
    "sample_size",
    "context",
)
ANSWERS = ("yes", "no", "cannot_tell")
COMMON_PROBLEMS = (
    "wrong_value",
    "not_supported_by_abstract",
    "missing_from_extraction",
    "wrong_group_time",
)
RESULT_PROBLEMS = COMMON_PROBLEMS + (
    "wrong_direction",
    "wrong_exposure_outcome",
    "planned_as_observed",
)
FACTORS = (
    "population",
    "region",
    "disease_subtype",
    "design",
    "comparator",
    "molecule_class",
    "dose",
    "duration",
    "outcome_definition",
    "biological_sample",
    "statistical_analysis",
    "sample_size",
    "other",
    "missing_context",
    "cannot_determine",
)


def _object(value, required=(), optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys():
        raise ValueError("Incomplete answer path")
    if value.keys() - set(required) - set(optional):
        raise ValueError("Unexpected or obsolete answer branch")
    return value


def _choice(value, choices):
    if not isinstance(value, str) or value not in choices:
        raise ValueError("Invalid answer choice")
    return value


def _detail(value, required=False):
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError("Invalid explanation")
    value = value.strip()
    if required and not value:
        raise ValueError("Explain the other difference")
    return value


def _factor(value, detail=""):
    _choice(value, FACTORS)
    if value in ("missing_context", "cannot_determine"):
        return "unknown", value
    if value in ("statistical_analysis", "sample_size"):
        return "other", value
    if value == "other":
        return "other", _detail(detail, required=True)
    if value == "biological_sample":
        # Clearer answer code; the exported legacy factor keeps the shared taxonomy name.
        if detail:
            raise ValueError("Explanation without an other difference")
        return "sample", ""
    if detail:
        raise ValueError("Explanation without an other difference")
    return value, ""


def validate_path(path, rationale=""):
    """Validate a complete path, reject stale branches, derive its terminal label.

    A material identified error takes precedence over uncertainty on the other
    side.  Supporting errors remain diagnostics and do not force extraction_error.
    """
    _object(path, ("q1",), ("q1_relevance", "q2", "q2_primary", "q3", "q4", "q5"))
    if not isinstance(rationale, str) or len(rationale) > 1500:
        raise ValueError("Invalid note")
    q1 = _object(path["q1"], ("a", "b"))
    has_error = False
    has_uncertainty = False
    problems = {"a": {}, "b": {}}
    canonical = {"q1": {"a": {}, "b": {}}}
    allowed = {"q1"}
    for side in ("a", "b"):
        rows = _object(q1[side], FIELDS)
        for field in FIELDS:
            row = _object(rows[field], ("answer", "problems"))
            answer = _choice(row["answer"], ANSWERS)
            choices = row["problems"]
            permitted = RESULT_PROBLEMS if field == "result" else COMMON_PROBLEMS
            if not isinstance(choices, list) or any(not isinstance(x, str) for x in choices):
                raise ValueError("Invalid field problems")
            if len(choices) != len(set(choices)) or any(x not in permitted for x in choices):
                raise ValueError("Invalid field problems")
            if (answer == "no") != bool(choices):
                raise ValueError("A No needs a problem; other answers cannot have problems")
            has_error |= answer == "no"
            has_uncertainty |= answer == "cannot_tell"
            clean = {"answer": answer, "problems": [x for x in permitted if x in choices]}
            canonical["q1"][side][field] = clean
            if answer != "yes":
                problems[side][field] = clean

    def finish(label, factor="none", detail="", relevance="not_needed"):
        if path.keys() - allowed:
            raise ValueError("Unexpected or obsolete answer branch")
        return {
            "instrument_version": INSTRUMENT_VERSION,
            "label": label,
            "factor": factor,
            "binary_inconsistent": label
            in ("not_replicated", "apparent_contradiction", "contradictory"),
            "rationale": rationale.strip(),
            "path": canonical,
            "field_problems": problems,
            "relevance": relevance,
            "other_detail": detail,
        }

    relevance = "not_needed"
    if has_error or has_uncertainty:
        allowed.add("q1_relevance")
        relevance = _choice(
            path.get("q1_relevance"), ("material", "not_material", "cannot_establish_comparison")
        )
        canonical["q1_relevance"] = relevance
        if relevance == "material":
            if not has_error:
                raise ValueError("An extraction error requires an identified problem")
            return finish("extraction_error", relevance=relevance)
        if relevance == "cannot_establish_comparison":
            return finish("not_comparable", "unknown", relevance=relevance)
    elif "q1_relevance" in path:
        raise ValueError("Relevance is only asked for a problem or uncertainty")

    allowed.add("q2")
    q2 = _object(path.get("q2"), ("exposure", "outcome", "comparison"))
    canonical["q2"] = {}
    failures = {}
    for field in ("exposure", "outcome", "comparison"):
        row = _object(q2[field], ("answer",), ("reason", "detail"))
        answer = _choice(row["answer"], ANSWERS)
        clean = {"answer": answer}
        if answer == "yes":
            if row.keys() - {"answer"}:
                raise ValueError("A matching check cannot have a reason")
        elif answer == "cannot_tell":
            if row.keys() - {"answer"}:
                raise ValueError("Uncertainty has no selected context difference")
            failures[field] = ("unknown", "")
        else:
            reason = row.get("reason")
            detail = _detail(row.get("detail", ""))
            if field == "exposure":
                _choice(reason, ("different_exposure", "molecule_class"))
                if detail:
                    raise ValueError("Unexpected exposure detail")
                failures[field] = (
                    ("other", "different_exposure")
                    if reason == "different_exposure"
                    else ("molecule_class", "")
                )
            elif field == "outcome":
                _choice(reason, ("outcome_definition",))
                if detail:
                    raise ValueError("Unexpected outcome detail")
                failures[field] = ("outcome_definition", "")
            else:
                failures[field] = _factor(reason, detail)
            clean["reason"] = reason
            if reason == "other":
                clean["detail"] = detail
            elif "detail" in row:
                raise ValueError("Unexpected detail")
        canonical["q2"][field] = clean
    if failures:
        allowed.add("q2_primary")
        primary = path.get("q2_primary")
        if primary is None and len(failures) == 1:
            primary = next(iter(failures))
        _choice(primary, failures)
        canonical["q2_primary"] = primary
        factor, detail = failures[primary]
        return finish("not_comparable", factor, detail, relevance)
    if "q2_primary" in path:
        raise ValueError("No failed comparison check to select")

    allowed.add("q3")
    q3 = _choice(path.get("q3"), ANSWERS)
    canonical["q3"] = q3
    if q3 == "yes":
        return finish("concordant", relevance=relevance)
    if q3 == "cannot_tell":
        return finish("not_comparable", "unknown", relevance=relevance)
    allowed.add("q4")
    q4 = _choice(path.get("q4"), ("effect_vs_no_effect", "opposite", "size_only", "insufficient"))
    canonical["q4"] = q4
    if q4 == "effect_vs_no_effect":
        return finish("not_replicated", relevance=relevance)
    if q4 == "size_only":
        return finish("concordant", relevance=relevance)
    if q4 == "insufficient":
        return finish("not_comparable", "unknown", relevance=relevance)
    allowed.add("q5")
    q5 = _object(path.get("q5"), ("answer",), ("factor", "detail"))
    answer = _choice(q5["answer"], ANSWERS)
    canonical["q5"] = {"answer": answer}
    if answer != "yes":
        if q5.keys() - {"answer"}:
            raise ValueError("A difference can only be selected after Yes")
        return finish(
            "contradictory" if answer == "no" else "not_comparable",
            "none" if answer == "no" else "unknown",
            relevance=relevance,
        )
    factor, detail = _factor(q5.get("factor"), _detail(q5.get("detail", "")))
    if "detail" in q5 and q5["factor"] != "other":
        raise ValueError("Unexpected detail")
    canonical["q5"]["factor"] = q5["factor"]
    if q5["factor"] == "other":
        canonical["q5"]["detail"] = detail
    return finish(
        "not_comparable" if factor == "unknown" else "apparent_contradiction",
        factor,
        detail,
        relevance,
    )


def parse_answer(form):
    raw = form.get("path", "")
    if not isinstance(raw, str) or len(raw) > 14000:
        raise ValueError("Invalid answer path")
    try:
        path = json.loads(raw)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError("Invalid answer path") from error
    return validate_path(path, form.get("rationale", ""))


def make_path(label, factor="population"):
    """Complete example paths for synthetic fixtures, never prefilled in the UI."""
    path = {
        "q1": {
            side: {field: {"answer": "yes", "problems": []} for field in FIELDS}
            for side in ("a", "b")
        }
    }
    if label == "extraction_error":
        path["q1"]["a"]["result"] = {"answer": "no", "problems": ["wrong_direction"]}
        path["q1_relevance"] = "material"
        return path
    path["q2"] = {field: {"answer": "yes"} for field in ("exposure", "outcome", "comparison")}
    if label == "not_comparable":
        path["q2"]["outcome"] = {"answer": "no", "reason": "outcome_definition"}
        path["q2_primary"] = "outcome"
        return path
    path["q3"] = "yes" if label == "concordant" else "no"
    if label == "concordant":
        return path
    path["q4"] = "effect_vs_no_effect" if label == "not_replicated" else "opposite"
    if label == "not_replicated":
        return path
    if label == "contradictory":
        path["q5"] = {"answer": "no"}
    elif label == "apparent_contradiction":
        path["q5"] = {"answer": "yes", "factor": factor}
    else:
        raise ValueError("Unknown label")
    return path


COPY = {
    "en": {
        "heading": "Check one finding from each abstract, then compare them.",
        "help": "Use the abstracts shown here. You do not need full texts or other studies.",
        "yes": "Yes",
        "no": "No",
        "cannot_tell": "Cannot tell",
        "q1_title": "Does this extracted finding match abstract {side}?",
        "q1_help": "Check every row, including fields marked “Not extracted” or “Not reported”.",
        "q1_absence": "A field showing “Not extracted” or “Not reported” is correct only when the abstract does not give that information. If the abstract gives it but the extraction leaves it out, choose “No” in that row. A field that does not concern this finding, for example the dose in a study of a biomarker, is correct if it is empty; it is wrong if it contains a value the abstract does not give. “Cannot tell” means the text does not let you judge, not that the information is missing.",
        "rows": [
            ("result", "Finding: what was studied, measured and found."),
            (
                "comparison",
                "Comparison: between groups, a change from baseline, or an association.",
            ),
            (
                "significance",
                "Statistical evidence: the p-value, interval or wording supports the extracted finding.",
            ),
            ("analysis", "Study and analysis, including adjustment or separate subgroup analyses."),
            ("groups", "People or groups, including the subgroup for this finding."),
            ("sample_size", "Sample size: the number and the group it refers to."),
            ("context", "Context: dose, duration, place and biological material."),
        ],
        "problem_title": "What is wrong? Select all that apply.",
        "problems": [
            ("wrong_value", "A value or wording differs from the abstract"),
            ("not_supported_by_abstract", "Not supported by the abstract"),
            ("missing_from_extraction", "A value or exception given in the abstract is missing"),
            ("wrong_group_time", "Wrong group or time point"),
            ("wrong_direction", "Wrong direction"),
            ("wrong_exposure_outcome", "Wrong exposure or outcome"),
            ("planned_as_observed", "A planned result is presented as observed"),
        ],
        "q1_relevance_title": "Does the extraction error change the finding or the comparison?",
        "q1_relevance_help": "Answer by looking at the extracted data. Choose “Yes, it changes the finding or the comparison” also when the error prevents a correct comparison of the two findings, for example a wrong exposure or outcome. A missing sample size or place is an error, but the finding usually stays the same. If one finding has an error that changes it, choose “Yes, it changes the finding or the comparison” even if the other is uncertain. “I cannot establish what is being compared” appears only when the problem concerns the “Finding” or “Comparison” row. A secondary finding extracted correctly is not an extraction error. Here the finding means what the extraction says was observed in one abstract, not your judgement on the comparison of the two studies.",
        "relevance_notice": "In the “Finding” row you marked an error that usually changes the finding. Check again: if the extraction reports a different finding from the abstract, choose “Yes, it changes the finding or the comparison”.",
        "relevance_options": [
            ("material", "Yes, it changes the finding or the comparison"),
            ("not_material", "No, the finding and the comparison stay the same"),
            ("cannot_establish_comparison", "I cannot establish what is being compared"),
        ],
        "q2_frame": "Now compare the two findings. The extraction tells you which findings to compare; to answer, use what the abstracts report, even where the extraction is incomplete. You have already reported extraction errors in the previous part.",
        "key_rule_label": "Key rule",
        "key_rules": {
            "q1_sample_size": "If the abstract gives only the sizes of the groups (for example 40 cases and 45 controls), “Not extracted” under “Whole study” is correct: groups are not added up. If the abstract states a total, or the size of the “Study population” or the “Comparison group”, and it is missing here, in the “Sample size” row choose “No” and, at the question “What is wrong?” that appears below, “A value or exception given in the abstract is missing”.",
            "q1_significance": "“Significance according to the authors” shows only what the authors state: in words, such as “significant” or “not significant”, or by setting a threshold, such as “p < 0.05 was considered significant”. If the abstract gives only numbers, such as a p-value or an interval, “Not reported” in that field is correct: significance is not inferred from the numbers, which you find in the “p-value” and “Confidence interval” fields. If instead a p-value, an interval or a statement about significance given in the abstract is missing from the extraction, in the “Statistical evidence” row choose “No” and, at the question “What is wrong?” that appears below, “A value or exception given in the abstract is missing”.",
            "q1_result": "The finding shown may be a secondary one: if it is extracted correctly, it is not an error. If the abstract reports an effect or association and the extraction says there is none, or the reverse, in the “Finding” row choose “No” and, at the question “What is wrong?” that appears below, “Not supported by the abstract”.",
            "q1_relevance": "Choose “Yes, it changes the finding or the comparison” if, because of that error, the extracted data report a finding different from the abstract, for example a reversed direction, a “no effect” that the abstract does not support or an invented comparison group. Choose “No, the finding and the comparison stay the same” if the error concerns a detail, such as a missing sample size.",
            "q2_exposure": "The same substance measured in different materials, for example serum and plasma, is the same exposure: choose “Yes”.",
            "q2_comparison": "Different populations or methods are not enough: choose “No” only if the two findings answer different questions. If one study finds the effect and the other does not, the findings remain comparable: choose “Yes”. If the findings then turn out to be opposite, you can report the difference in the last question.",
            "q3": "Before answering, reread the conclusion of each abstract: expressions such as “not significant”, “no better”, “did not” or “no difference” indicate an effect that was not confirmed. If one study reports an effect and the other does not find or confirm it, choose “No”, even if the estimates point in the same direction.",
            "q4": "If one of the studies does not find or confirm the effect, it is not an opposite effect: choose “One reports an effect or association; the other reports no effect or does not confirm it”.",
        },
        "q2_title": "Can these two findings be compared?",
        "q2_rows": [
            ("exposure", "Do they concern the same exposure or intervention?"),
            ("outcome", "Do they measure the same outcome?"),
            ("comparison", "Are the measurements and comparisons similar enough?"),
        ],
        "q2_help": "Check the reference group, measurement and time point. Different populations or methods alone do not make the findings non-comparable: choose “No” only if the two findings answer different questions. If the question is the same, choose “Yes”; if the findings then turn out to be opposite, you can report the difference in the final question. If one study finds the effect and the other does not, the findings remain comparable. Units that can be converted do not by themselves prevent comparison. A specific medicine and its class can be compared only when that comparison makes sense.",
        "reason": "What prevents comparison?",
        "exposure_reasons": [
            ("different_exposure", "Different exposures or interventions"),
            ("molecule_class", "A specific medicine versus a medicine class"),
        ],
        "comparison_reasons": [
            ("comparator", "Comparison group"),
            ("other", "Type of comparison or time of measurement"),
            ("outcome_definition", "How the outcome was defined or measured"),
        ],
        "outcome_reason": "The outcomes differ in what they measure or how they are defined.",
        "primary_reason": "Which of these is the main reason you cannot compare them?",
        "q3_title": "Do both studies report the same finding?",
        "q3_help": "Reread the conclusion of each abstract, not just the direction shown by the extraction. Choose “Yes” if both report the same direction, or both explicitly report no difference. Different effect sizes can still agree. A difference in statistical significance alone is not an opposite finding. If one study reports an effect and the other says it did not find or confirm it, choose “No”, even if the estimates point in the same direction.",
        "q4_title": "How do the results differ?",
        "q4_options": [
            (
                "effect_vs_no_effect",
                "One reports an effect or association; the other reports no effect or does not confirm it",
            ),
            ("opposite", "Both find an effect or association, but in opposite directions"),
            ("size_only", "They differ only in size, not in direction or conclusion"),
            ("insufficient", "The abstracts do not give enough information to decide"),
        ],
        "q4_help": "Choose what the abstracts conclude. Reporting no effect or not confirming an effect is different from reporting the opposite effect. Choose “Both find an effect or association, but in opposite directions” only if both studies find an effect.",
        "q5_title": "Do the abstracts describe a difference that could explain the opposite findings?",
        "q5_help": "Compare what each abstract says about its own study. The authors do not need to discuss the other study. Choose a difference supported by the texts, not an explanation from outside knowledge. If you choose “Yes”, choose the difference at the question “Which difference could explain this?” that appears below. Choose “No” when the studies are described well enough but you find no explanation. If essential details are missing, choose “Cannot tell”.",
        "q5_factor": "Which difference could explain this?",
        "q5_factor_help": "Choose the best-supported difference. A different sample size alone is not enough: it must help explain the finding. You can mention other differences in the optional note.",
        "factors": [
            ("population", "People studied: age, sex or other conditions"),
            ("region", "Where participants were recruited"),
            ("disease_subtype", "Disease subtype"),
            ("design", "Study design"),
            ("comparator", "Comparison group"),
            ("molecule_class", "A specific medicine versus a medicine class"),
            ("dose", "Dose"),
            ("duration", "Duration or follow-up"),
            ("outcome_definition", "How the outcome was defined or measured"),
            ("biological_sample", "Biological material, such as serum or plasma"),
            ("statistical_analysis", "Statistical analysis or adjustment"),
            ("sample_size", "Sample size, when it helps explain the finding"),
            ("other", "Another difference"),
            ("missing_context", "Not stated: essential context is missing"),
            ("cannot_determine", "Cannot determine from these abstracts"),
        ],
        "other_detail": "Briefly describe the difference",
        "select": "Choose an answer",
        "next": "Continue",
        "back": "Back",
        "review": "Your answers are ready to save",
        "review_help": "To change an answer, press “Change” next to it before saving.",
        "review_choices": "Review your choices",
        "note": "Optional note about these findings",
        "note_help": "When a choice does not convince you, or you pick an unusual option, write a few words in the note: they are very useful for the analysis. You can also mention another difference or another finding omitted from the extraction.",
        "save": "Save and continue",
        "draft": "Your draft is saved on this device when browser storage is available. It is removed after the server confirms your answer.",
        "error": "Complete each visible row. For every “No”, choose what is wrong or why the findings cannot be compared.",
        "no_identified_error": "To choose “Yes, it changes the finding or the comparison”, first choose “No” in at least one row of A or B.",
        "keyboard": "Use Tab and the arrow keys to move through the visible choices. Shortcuts never skip a question.",
        "no_js": "JavaScript is needed to follow the question path. Enable it and reload; no answer has been sent.",
        "block": "Question",
        "note_saved": "Your answer will include this comment.",
    },
    "it": {
        "heading": "Controlla un risultato per ciascun abstract, poi confrontali.",
        "help": "Usa gli abstract qui sotto. Non servono gli articoli completi né altri studi.",
        "yes": "Sì",
        "no": "No",
        "cannot_tell": "Non posso stabilirlo",
        "q1_title": "Il risultato estratto corrisponde all’abstract {side}?",
        "q1_help": "Controlla tutte le righe, anche i campi indicati come «Non estratto» o «Non riportato».",
        "q1_absence": "Un campo «Non estratto» o «Non riportato» è corretto solo se l’abstract non riporta quell’informazione. Se l’informazione è nell’abstract ma manca nell’estrazione, in quella riga scegli «No». Un campo che non riguarda questo risultato, per esempio la dose in uno studio su un biomarcatore, è corretto se è vuoto; è sbagliato se contiene un valore che l’abstract non riporta. «Non posso stabilirlo» significa che il testo non ti permette di giudicare, non che l’informazione manca.",
        "rows": [
            ("result", "Risultato: cosa è stato studiato, misurato e osservato."),
            ("comparison", "Confronto: tra gruppi, rispetto al valore iniziale o associazione."),
            (
                "significance",
                "Evidenza statistica: il p-value, l’intervallo o le parole degli autori sostengono il risultato estratto.",
            ),
            (
                "analysis",
                "Studio e analisi, compresi gli aggiustamenti e le analisi separate dei sottogruppi.",
            ),
            (
                "groups",
                "Persone o gruppi, compreso il sottogruppo a cui si riferisce il risultato.",
            ),
            ("sample_size", "Numerosità: il numero e il gruppo a cui si riferisce."),
            ("context", "Contesto: dose, durata, luogo e materiale biologico."),
        ],
        "problem_title": "Qual è il problema? Puoi scegliere più risposte.",
        "problems": [
            ("wrong_value", "Un valore o una formulazione è diverso dall’abstract"),
            ("not_supported_by_abstract", "L’abstract non lo sostiene"),
            ("missing_from_extraction", "Manca un dato o un’eccezione che l’abstract riporta"),
            ("wrong_group_time", "Gruppo o momento della misura errati"),
            ("wrong_direction", "Direzione del risultato invertita"),
            ("wrong_exposure_outcome", "Esposizione o esito errati"),
            ("planned_as_observed", "Un risultato atteso è presentato come osservato"),
        ],
        "q1_relevance_title": "L’errore di estrazione cambia il risultato o il confronto?",
        "q1_relevance_help": "Rispondi guardando i dati estratti. Scegli «Sì, cambia il risultato o il confronto» anche quando l’errore non permette di confrontare correttamente i due risultati, per esempio un’esposizione o una variabile misurata sbagliate. Una numerosità o un luogo mancanti sono errori, ma di solito il risultato resta lo stesso. Se in uno dei due risultati c’è un errore che lo cambia, scegli «Sì, cambia il risultato o il confronto» anche se l’altro è incerto. «Non riesco a stabilire cosa si sta confrontando» compare solo se il problema riguarda la riga «Risultato» o «Confronto». Un risultato secondario estratto correttamente non è un errore di estrazione. Qui per risultato si intende ciò che l’estrazione dice di aver osservato in un abstract, non il giudizio sul confronto tra i due studi.",
        "relevance_notice": "Nella riga «Risultato» hai segnato un errore che di solito cambia il risultato. Ricontrolla: se l’estrazione riporta un risultato diverso da quello dell’abstract, scegli «Sì, cambia il risultato o il confronto».",
        "relevance_options": [
            ("material", "Sì, cambia il risultato o il confronto"),
            ("not_material", "No, il risultato e il confronto restano gli stessi"),
            ("cannot_establish_comparison", "Non riesco a stabilire cosa si sta confrontando"),
        ],
        "q2_frame": "Ora confronti i due risultati. L’estrazione ti indica quali risultati confrontare; per rispondere usa ciò che riportano gli abstract, anche dove l’estrazione è incompleta. Gli errori dell’estrazione li hai già segnalati nella parte precedente.",
        "key_rule_label": "Attenzione",
        "key_rules": {
            "q1_sample_size": "Se l’abstract riporta solo la numerosità dei gruppi (per esempio 40 casi e 45 controlli), «Non estratto» in «Intero studio» è corretto: i gruppi non vanno sommati. Se l’abstract scrive un totale, o la numerosità della «Popolazione in studio» o del «Gruppo di confronto», e qui manca, nella riga «Numerosità» scegli «No» e, alla domanda «Qual è il problema?» che compare sotto, «Manca un dato o un’eccezione che l’abstract riporta».",
            "q1_significance": "«Significatività secondo gli autori» riporta solo ciò che dichiarano gli autori: a parole, come «significativo» o «non significativo», oppure fissando una soglia, come «p < 0,05 è stato considerato significativo». Se l’abstract dà solo numeri, come un p-value o un intervallo, «Non riportato» in quel campo è corretto: la significatività non va dedotta dai numeri, che trovi nei campi «p-value» e «Intervallo di confidenza». Se invece nell’estrazione manca un p-value, un intervallo o una frase sulla significatività presente nell’abstract, nella riga «Evidenza statistica» scegli «No» e, alla domanda «Qual è il problema?» che compare sotto, «Manca un dato o un’eccezione che l’abstract riporta».",
            "q1_result": "Il risultato mostrato può essere secondario: se è estratto correttamente, non è un errore. Se l’abstract riporta un effetto o un’associazione e l’estrazione dice che non c’è, o il contrario, nella riga «Risultato» scegli «No» e, alla domanda «Qual è il problema?» che compare sotto, «L’abstract non lo sostiene».",
            "q1_relevance": "Scegli «Sì, cambia il risultato o il confronto» se, per quell’errore, i dati estratti riportano un risultato diverso da quello dell’abstract, per esempio con la direzione invertita, un «nessun effetto» che l’abstract non sostiene o un gruppo di confronto inventato. Scegli «No, il risultato e il confronto restano gli stessi» se l’errore riguarda un dettaglio, come una numerosità mancante.",
            "q2_exposure": "La stessa sostanza misurata in materiali diversi, per esempio nel siero e nel plasma, è la stessa esposizione: scegli «Sì».",
            "q2_comparison": "Popolazioni o metodi diversi non bastano: scegli «No» solo se i due risultati rispondono a domande diverse. Se uno studio trova l’effetto e l’altro no, i risultati restano confrontabili: scegli «Sì». Se poi i risultati sono opposti, potrai indicare la differenza nell’ultima domanda.",
            "q3": "Prima di rispondere rileggi la conclusione di ciascun abstract: espressioni come «not significant», «no better», «did not» o «no difference» indicano un effetto non confermato. Se uno studio riporta un effetto e l’altro non lo trova o non lo conferma, scegli «No», anche se le stime vanno nella stessa direzione.",
            "q4": "Se uno dei due studi non trova o non conferma l’effetto, non è un effetto opposto: scegli «Uno riporta un effetto o un’associazione; l’altro non trova un effetto o non lo conferma».",
        },
        "q2_title": "Questi due risultati si possono confrontare?",
        "q2_rows": [
            ("exposure", "Riguardano la stessa esposizione o lo stesso intervento?"),
            ("outcome", "Misurano lo stesso esito, cioè la stessa variabile?"),
            ("comparison", "Le misure e i confronti sono abbastanza simili?"),
        ],
        "q2_help": "Controlla il gruppo di riferimento, la misura e il momento in cui è stata fatta. Popolazioni o metodi diversi non bastano da soli a rendere i risultati non confrontabili: scegli «No» solo se i due risultati rispondono a domande diverse. Se la domanda è la stessa, scegli «Sì»; se poi i risultati sono opposti, potrai indicare la differenza nella domanda finale. Se uno studio trova l’effetto e l’altro no, i risultati restano confrontabili. Unità convertibili non impediscono da sole il confronto. Un farmaco e la sua classe si possono confrontare solo quando il confronto ha senso.",
        "reason": "Cosa impedisce il confronto?",
        "exposure_reasons": [
            ("different_exposure", "Esposizioni o interventi diversi"),
            ("molecule_class", "Un farmaco specifico rispetto a una classe di farmaci"),
        ],
        "comparison_reasons": [
            ("comparator", "Gruppo di confronto"),
            ("other", "Tipo di confronto o momento della misura"),
            ("outcome_definition", "Definizione o misura dell’esito"),
        ],
        "outcome_reason": "Gli esiti differiscono per ciò che misurano o per come sono definiti.",
        "primary_reason": "Qual è il motivo principale per cui non puoi confrontarli?",
        "q3_title": "I due studi riportano lo stesso risultato?",
        "q3_help": "Rileggi la conclusione di ciascun abstract, non solo la direzione mostrata dall’estrazione. Scegli «Sì» se i risultati vanno nella stessa direzione, oppure se entrambi dichiarano di non aver trovato differenze. Effetti di entità diversa possono concordare. Una differenza nella sola significatività statistica non è un risultato opposto. Se uno studio riporta un effetto e l’altro dice di non averlo trovato o confermato, scegli «No» anche se le stime vanno nella stessa direzione.",
        "q4_title": "In cosa differiscono i risultati?",
        "q4_options": [
            (
                "effect_vs_no_effect",
                "Uno riporta un effetto o un’associazione; l’altro non trova un effetto o non lo conferma",
            ),
            ("opposite", "Entrambi trovano un effetto o un’associazione, ma in direzioni opposte"),
            ("size_only", "Differiscono solo per entità, non per direzione o conclusione"),
            ("insufficient", "Gli abstract non danno informazioni sufficienti per decidere"),
        ],
        "q4_help": "Considera le conclusioni degli abstract. Non trovare o non confermare un effetto è diverso dal trovare l’effetto opposto. Scegli «Entrambi trovano un effetto o un’associazione, ma in direzioni opposte» solo se entrambi gli studi trovano un effetto.",
        "q5_title": "Negli abstract c’è una differenza che potrebbe spiegare i risultati opposti?",
        "q5_help": "Confronta ciò che ogni abstract dice del proprio studio. Gli autori non devono discutere l’altro studio. Scegli una differenza sostenuta dai testi, senza ricorrere a spiegazioni esterne. Se scegli «Sì», indica la differenza alla domanda «Quale differenza potrebbe spiegarli?» che compare sotto. Scegli «No» se gli studi sono descritti abbastanza bene ma non trovi una spiegazione. Se mancano dettagli essenziali, scegli «Non posso stabilirlo».",
        "q5_factor": "Quale differenza potrebbe spiegarli?",
        "q5_factor_help": "Scegli la differenza meglio sostenuta dai testi. Una numerosità diversa non basta da sola: deve aiutare a spiegare il risultato. Puoi citare altre differenze nella nota facoltativa.",
        "factors": [
            ("population", "Persone studiate: età, sesso o altre condizioni"),
            ("region", "Luogo di reclutamento"),
            ("disease_subtype", "Sottotipo della malattia"),
            ("design", "Disegno dello studio"),
            ("comparator", "Gruppo di confronto"),
            ("molecule_class", "Un farmaco specifico rispetto a una classe di farmaci"),
            ("dose", "Dose"),
            ("duration", "Durata o periodo di osservazione"),
            ("outcome_definition", "Definizione o misura dell’esito"),
            ("biological_sample", "Materiale biologico, come siero o plasma"),
            ("statistical_analysis", "Analisi statistica o aggiustamenti"),
            ("sample_size", "Numerosità, se aiuta a spiegare il risultato"),
            ("other", "Un’altra differenza"),
            ("missing_context", "Non indicato: mancano informazioni essenziali sul contesto"),
            ("cannot_determine", "Non si può stabilire da questi abstract"),
        ],
        "other_detail": "Descrivi brevemente la differenza",
        "select": "Scegli una risposta",
        "next": "Continua",
        "back": "Indietro",
        "review": "Le risposte sono pronte per l’invio",
        "review_help": "Per cambiare una risposta, premi «Modifica» accanto a essa prima di salvare.",
        "review_choices": "Rivedi le tue scelte",
        "note": "Nota facoltativa su questi risultati",
        "note_help": "Quando una scelta non ti convince, o scegli un’opzione insolita, scrivi due parole nella nota: per l’analisi sono molto utili. Puoi anche citare un’altra differenza o un altro risultato omesso dall’estrazione.",
        "save": "Salva e continua",
        "draft": "La bozza viene salvata su questo dispositivo, se il browser lo consente. Viene cancellata quando il server conferma la risposta.",
        "error": "Completa tutte le righe visibili. Per ogni «No», indica il problema o il motivo che impedisce il confronto.",
        "no_identified_error": "Per scegliere «Sì, cambia il risultato o il confronto», scegli prima «No» in almeno una riga di A o B.",
        "keyboard": "Usa Tab e le frecce per spostarti tra le scelte visibili. Le scorciatoie non saltano domande.",
        "no_js": "Per seguire le domande serve JavaScript. Attivalo e ricarica la pagina: nessuna risposta è stata inviata.",
        "block": "Domanda",
        "note_saved": "Il commento sarà salvato insieme alla risposta.",
    },
}


def instrument_copy(lang):
    from .guidance import guidance_copy

    return {**COPY[lang], **guidance_copy(lang)}
