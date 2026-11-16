# SPDX-License-Identifier: AGPL-3.0-only
"""Bilingual UI copy. Scientific source terms stay in their source language."""

LABELS = {
    "it": [
        "Errore di estrazione",
        "Non confrontabili",
        "Concordi",
        "Risultato non replicato",
        "Contraddizione apparente",
        "Contraddizione diretta",
    ],
    "en": [
        "Extraction error",
        "Not comparable",
        "Concordant",
        "Not replicated",
        "Apparent contradiction",
        "Direct contradiction",
    ],
}


FACTORS = {
    "it": [
        "Popolazione",
        "Regione",
        "Sottotipo di malattia",
        "Disegno dello studio",
        "Gruppo di confronto",
        "Molecola / classe",
        "Dose",
        "Durata",
        "Definizione dell’esito",
        "Campione biologico",
        "Nessuno",
        "Contesto non determinabile",
        "Altro (specificare)",
    ],
    "en": [
        "Population",
        "Region",
        "Disease subtype",
        "Study design",
        "Comparison group",
        "Molecule / class",
        "Dose",
        "Duration",
        "Outcome definition",
        "Biological sample",
        "None",
        "Context cannot be determined",
        "Other (specify)",
    ],
}


UI = {
    "it": {
        "tagline": "Un piccolo contributo alla ricerca",
        "preview_privacy": "Nella versione di prova, i commenti facoltativi, la schermata di "
        "riferimento e l’orario sono conservati separatamente per migliorare "
        "l’interfaccia.",
        "preview_banner": "Anteprima: le risposte non vengono conteggiate né pagate",
        "feedback_prompt": "Commenti per l’autore dello studio: cosa non è chiaro, cosa cambieresti?",
        "feedback_send": "Invia commento",
        "feedback_saved": "Grazie, il commento è stato salvato.",
        "rules": "Regole e compenso",
        "guidelines": "Guida completa",
        "privacy": "Privacy",
        "start": "Inizia",
        "resume": "Riprendi",
        "theme": "Tema",
        "light": "Chiaro",
        "dark": "Scuro",
        "hero": "Leggi la ricerca.\nAiutaci a capirla.",
        "intro": "Confronta i risultati di due abstract della letteratura sulle malattie metaboliche (diabete, obesità, sindrome metabolica) e aiutaci a valutare quanto è "
        "affidabile un sistema che li estrae e li confronta.",
        "time": "Puoi fare pause. Non serve un account.",
        "payline": "{price} per coppia completata · pagamento da {minimum} coppie in su.",
        "eligible": "Per studenti e laureati maggiorenni dell’Università di Pisa",
        "excluded_programmes": "Le risposte di chi non ha questi requisiti non vengono usate né "
        "pagate.",
        "limited": "Una partecipazione a persona. Posti limitati, in ordine di arrivo.",
        "voluntary": "Partecipazione volontaria. Leggi l’informativa prima di iniziare.",
        "project": "Studio condotto da uno studente sulla lettura automatica della letteratura sulle malattie metaboliche",
        "independent": "Non è un servizio ufficiale di un’università.",
        "contact": "Un dubbio? Scrivi a",
        "resume_title": "Hai già iniziato?",
        "code": "Codice personale",
        "resume_help": "Inserisci il codice di 8 caratteri. Non serve nome o email.",
        "code_help": "Conserva il codice per riprendere la sessione e richiedere il compenso. "
        "Invialo privatamente sul canale in cui hai ricevuto il link, oppure via "
        "email.",
        "code_missing": "Il codice non è salvato su questo browser. Puoi crearne uno nuovo qui: "
        "sostituirà quello precedente.",
        "new_code": "Crea un nuovo codice",
        "copy": "Copia codice",
        "copied": "Copiato",
        "your_code": "Il tuo codice",
        "continue": "Continua",
        "back": "Indietro",
        "yes": "Sì",
        "no": "No",
        "submit": "Salva e continua",
        "saved": "Risposta salvata.",
        "draft": "La bozza resta in questo browser. La risposta è salvata sul server solo dopo "
        "l’invio.",
        "finish": "Termina la sessione",
        "finish_short": "Termina",
        "done": "coppie completate",
        "earned": "maturati",
        "minimum": "Pagamento da {minimum} coppie in su",
        "fixed_progress": "Compenso fisso: {fee} da {minimum} coppie",
        "fixed_unlocked": "Compenso fisso maturato",
        "pair": "Confronto",
        "sources": "Fonte e record",
        "source": "Da PubMed (U.S. National Library of Medicine)",
        "source_unavailable": "Record esterno non disponibile",
        "abstract": "Abstract completo",
        "evidence": "Frasi di evidenza evidenziate e numerate",
        "claim": "Quello che il sistema ha estratto",
        "technical": "Dettagli tecnici",
        "significant_chip": "Risultato statisticamente significativo",
        "nonsignificant_chip": "Differenza non statisticamente significativa",
        "unknown_significance": "Significatività non estratta",
        "hedged_chip": "Detto in forma ipotetica dagli autori («potrebbe», «suggerisce»)",
        "evidence_sentence": "Evidenza: frase",
        "class_chip": "Classe",
        "claim_hint": "Controlla il risultato estratto confrontandolo con l’abstract.",
        "sign": "Segno",
        "kind": "Tipo",
        "comparator": "Comparatore",
        "context": "Contesto",
        "significant": "Significativo",
        "hedged": "Formulazione cauta",
        "unknown": "Non riportato",
        "exposure_class": "Classe dell’esposizione",
        "decision": "Il tuo giudizio",
        "decision_hint": "Controlla un risultato per abstract, poi confrontali.",
        "factor": "Differenza principale",
        "factor_hint": "Scegli una differenza pertinente e sostenuta dagli abstract.",
        "select": "Scegli una differenza",
        "factor_other": "Specifica la differenza",
        "rationale": "Nota facoltativa",
        "rationale_placeholder": "Se vuoi, indica un dettaglio utile a capire la tua risposta.",
        "side": "Dove hai notato l’errore? (facoltativo)",
        "both": "Entrambi",
        "chip_help": "Che cosa significa",
        "keyboard": "Usa Tab per spostarti e i tasti indicati per le scelte visibili.",
        "missing_context": "Se manca un’informazione essenziale per il confronto, scegli «Non "
        "posso stabilirlo».",
        "practice": "Una coppia per prendere confidenza",
        "practice_intro": "Questo esempio è inventato. Dopo la risposta vedrai una spiegazione. "
        "Nella raccolta retribuita conta come una coppia.",
        "feedback": "Un esempio, passo per passo",
        "correct": "Risposta corretta",
        "your_answer": "La tua risposta",
        "practice_next": "Vai alle prossime coppie",
        "tutorial": "Come leggere una coppia",
        "tutorial_next": "Ho letto, continua",
        "qualification": "Prova iniziale",
        "qualification_intro": "Sei brevi esempi inventati. Servono {pass_count} risposte corrette "
        "per continuare. Hai due tentativi; questa prova non conta come "
        "coppia retribuita.",
        "question": "Domanda",
        "qualification_feedback": "Le risposte della prova",
        "passed": "Prova superata",
        "retry": "Riprova con sei esempi diversi",
        "failed": "Grazie per il tuo tempo. La prova non è stata superata; non riceverai "
        "assegnazioni.",
        "admit": "Inizia le coppie",
        "full": "I posti sono al momento esauriti",
        "full_help": "Grazie per l’interesse. Puoi riprovare più tardi: le disponibilità dipendono "
        "dalle letture ancora necessarie.",
        "try_again": "Controlla disponibilità",
        "batch_done": "Hai completato questo gruppo",
        "batch_help": "Premi «Altre coppie» per continuare, se ce ne sono, oppure «Termina la sessione».",
        "next_pair": "Prossima coppia",
        "next_pair_help": "Premi «Altre coppie» per ricevere la prossima, oppure «Termina la sessione».",
        "more": "Altre coppie",
        "quality_stop": "Grazie per il tuo contributo",
        "quality_help": "Non sono previste altre assegnazioni per questa sessione. Le risposte già "
        "completate restano registrate e valgono per il compenso secondo le "
        "regole.",
        "closed": "Raccolta chiusa, grazie",
        "closed_help": "La raccolta è chiusa. Le risposte salvate e i dati per il pagamento "
        "restano disponibili.",
        "surplus": "Grazie: la risposta è stata conservata, ma questa lettura non era più "
        "necessaria o disponibile. Non aggiunge compenso.",
        "finish_title": "Un ultimo passo",
        "finish_intro": "Questi dati identificano la tua partecipazione e servono a organizzare il "
        "pagamento.",
        "programme": "Corso di studi",
        "other": "Altro",
        "programme_help": "Se ti sei già laureata o laureato in uno di questi corsi, sceglilo e, come anno di corso, scrivi «laureata» o «laureato».",
        "other_programme": "Specifica il corso",
        "year": "Anno di corso",
        "year_placeholder": "Es. 3° anno, fuori corso, laureato",
        "finish_button": "Conferma e mostra il codice",
        "thanks": "Grazie. Il tuo contributo conta.",
        "final_help": "Conserva il codice per riprendere la sessione e richiedere il compenso. "
        "Invialo privatamente all’autore dello studio sul canale in cui hai ricevuto il link, "
        "oppure via email. Il pagamento si concorda personalmente alla fine dello "
        "studio, con la modalità che preferisci.",
        "payable": "Compenso da richiedere",
        "below_min": "Non hai raggiunto la soglia di {minimum} coppie: non è previsto un "
        "pagamento.",
        "review_programme": "Hai indicato un corso da verificare. Le risposte e il pagamento "
        "restano sospesi in attesa di autorizzazione.",
        "error": "Qualcosa non ha funzionato",
        "error_help": "Il modulo è scaduto o i dati non sono validi. Riapri la pagina e riprova: "
        "le risposte già salvate sono al sicuro.",
        "bad_code": "Codice non riconosciuto. Controlla gli 8 caratteri e riprova.",
        "rate_limit": "Troppi tentativi. Attendi 15 minuti prima di riprovare.",
        "too_large": "Il modulo supera la dimensione consentita. Accorcia il testo e riprova.",
        "return": "Torna alla tua sessione",
        "read_rules": "Iniziando dichiari di avere i requisiti, accetti le regole e dai il "
        "consenso dopo aver letto l’informativa.",
        "enabled_tutorial": "Prima di iniziare: una breve guida.",
        "enabled_qualification": "È prevista una prova iniziale di 6 coppie (almeno {pass_count} "
        "corrette, un secondo tentativo).",
        "enabled_practice": "La prima coppia, quando disponibile, è una prova con una "
        "spiegazione. La prova conta per il compenso; le altre sono coppie reali.",
        "fee_rule": "In più, {fee} fissi dopo {minimum} coppie completate.",
        "pay_rule": "{price} per coppia completata. Pagamento da {minimum} coppie in su.",
        "enabled_controls": "Durante il lavoro sono previsti controlli di qualità non segnalati, "
        "che contano per il compenso.",
        "correct_path": "Il percorso corretto",
        "no_ai": "Rispondi da solo, senza strumenti di intelligenza artificiale o aiuto di altre "
        "persone.",
        "pay_threshold_amount": "Al raggiungimento della soglia: {amount}.",
        "pay_practice_price": "La coppia di prova vale {practice}.",
        "eligibility_note": "Possono partecipare anche laureate e laureati in questi corsi: nel modulo finale, come anno di corso, scrivi «laureata» o «laureato».",
        "paid_tasks": "{count} coppie retribuite completate",
        "real_pairs": "{count} coppie reali completate",
        "accrued": "Maturato",
        "payable_from": "Pagamento da {minimum} coppie in su",
        "identity_help": "Questi dati identificano la tua partecipazione e servono a organizzare "
        "il pagamento.",
        "first_name": "Nome",
        "last_name": "Cognome",
        "eligibility_declaration": "Dichiaro di essere maggiorenne e iscritto/a all'Università di Pisa a uno dei corsi indicati, oppure laureato/a in uno di essi nello stesso ateneo",
        "finish_below_warning": "Hai completato {count} coppie retribuite su {minimum}. Se "
        "termini ora, non è previsto un pagamento. Puoi invece chiudere la "
        "pagina e riprendere più tardi con il tuo codice.",
        "finish_below_confirm": "Confermo di voler terminare sotto la soglia, senza richiedere un "
        "pagamento.",
        "finish_below_action": "Termina sotto la soglia",
        "resume_work": "Riprendi il lavoro",
        "closed_resume": "La raccolta è chiusa. Le risposte salvate e i dati per il pagamento "
        "restano disponibili.",
        "site_stop_exception": "Il sito ha interrotto le assegnazioni. Le coppie accettate in "
        "buona fede restano pagabili anche sotto la soglia.",
        "programme_review": "Hai indicato un corso da verificare. Le risposte e il pagamento "
        "restano sospesi in attesa di autorizzazione.",
        "next_work": "Continua con le coppie",
        "preview_rate_header": "Compenso previsto per la raccolta retribuita",
        "preview_tasks": "{count} coppie di prova completate",
        "collection_coverage": "{percent}% delle letture necessarie completato",
        "coverage_complete": "Tutte le coppie hanno le letture necessarie.",
        "coverage_incomplete": "La raccolta è chiusa, ma alcune coppie non hanno tutte le letture "
        "necessarie.",
        "coverage_summary": "Coppie con almeno due letture: {covered}/{total} · "
        "Con un giudizio finale: {resolved}/{total}",
        "update_details": "Aggiorna i tuoi dati",
        "cannot_tell": "Non si può stabilire",
        "not_extracted": "Non estratto",
        "not_reported": "Non riportato",
    },
    "en": {
        "tagline": "A small contribution to research",
        "preview_privacy": "In the preview, optional comments, the screen reference and timestamp "
        "are stored separately to improve the interface.",
        "preview_banner": "Preview: answers are not counted or paid",
        "feedback_prompt": "Comments for the study’s author: what is unclear, what would you change?",
        "feedback_send": "Send feedback",
        "feedback_saved": "Thank you, your feedback has been saved.",
        "rules": "Rules and pay",
        "guidelines": "Full guidelines",
        "privacy": "Privacy",
        "start": "Start",
        "resume": "Resume",
        "theme": "Theme",
        "light": "Light",
        "dark": "Dark",
        "hero": "Read the research.\nHelp us understand it.",
        "intro": "Compare findings from two abstracts on metabolic diseases (diabetes, obesity and metabolic syndrome) and help evaluate how reliably "
        "research results can be extracted and compared.",
        "time": "You can pause. No account needed.",
        "payline": "{price} per completed pair · payment from {minimum} pairs upwards.",
        "eligible": "For adult students and graduates of the University of Pisa",
        "excluded_programmes": "Answers from people who do not meet these requirements are not "
        "used or paid.",
        "limited": "One participation per person. Limited places, first come, first served.",
        "voluntary": "Participation is voluntary. Read the privacy notice before starting.",
        "project": "A study run by a student on the automated reading of the literature on metabolic diseases",
        "independent": "This is not an official university service.",
        "contact": "A question? Write to",
        "resume_title": "Already started?",
        "code": "Personal code",
        "resume_help": "Enter your 8-character code. No name or email needed.",
        "code_help": "Keep this code to resume your session and claim payment. Send it privately "
        "through the channel where you received the link, or by email.",
        "code_missing": "The code is not saved in this browser. You can create a new one here; it "
        "replaces the previous code.",
        "new_code": "Create a new code",
        "copy": "Copy code",
        "copied": "Copied",
        "your_code": "Your code",
        "continue": "Continue",
        "back": "Back",
        "yes": "Yes",
        "no": "No",
        "submit": "Save and continue",
        "saved": "Answer saved.",
        "draft": "Your draft stays in this browser. Your answer is saved to the server only when "
        "submitted.",
        "finish": "Finish the session",
        "finish_short": "Finish",
        "done": "pairs completed",
        "earned": "accrued",
        "minimum": "Payable from {minimum} pairs upwards",
        "fixed_progress": "Fixed fee: {fee} from {minimum} pairs",
        "fixed_unlocked": "Fixed fee earned",
        "pair": "Comparison",
        "sources": "Source and record",
        "source": "From PubMed (U.S. National Library of Medicine)",
        "source_unavailable": "External record unavailable",
        "abstract": "Full abstract",
        "evidence": "Evidence sentences highlighted and numbered",
        "claim": "What the system extracted",
        "technical": "Technical details",
        "significant_chip": "Statistically significant result",
        "nonsignificant_chip": "Difference not statistically significant",
        "unknown_significance": "Significance not extracted",
        "hedged_chip": 'Stated tentatively by the authors ("may", "suggests")',
        "evidence_sentence": "Evidence: sentence",
        "class_chip": "Class",
        "claim_hint": "Check the extracted finding against the abstract.",
        "sign": "Sign",
        "kind": "Kind",
        "comparator": "Comparator",
        "context": "Context",
        "significant": "Significant",
        "hedged": "Hedged wording",
        "unknown": "Not reported",
        "exposure_class": "Exposure class",
        "decision": "Your judgment",
        "decision_hint": "Check one finding per abstract, then compare them.",
        "factor": "Main difference",
        "factor_hint": "Choose a relevant difference supported by the abstracts.",
        "select": "Choose a difference",
        "factor_other": "Specify the difference",
        "rationale": "Optional note",
        "rationale_placeholder": "You can add a detail that helps explain your answer.",
        "side": "Where is the extraction error? (optional)",
        "both": "Both",
        "chip_help": "What this means",
        "keyboard": "Use Tab to move and the indicated keys for visible choices.",
        "missing_context": "If essential information for the comparison is missing, choose “Cannot "
        "tell”.",
        "practice": "One pair to get familiar",
        "practice_intro": "This example is invented. After answering, you will see an explanation. "
        "In the paid collection, it counts as one pair.",
        "feedback": "An example, step by step",
        "correct": "Correct answer",
        "your_answer": "Your answer",
        "practice_next": "Go to the next pairs",
        "tutorial": "How to read a pair",
        "tutorial_next": "I’ve read it, continue",
        "qualification": "Entry test",
        "qualification_intro": "Six short invented examples. You need {pass_count} correct answers "
        "to continue. You have two attempts; this test does not count as "
        "paid pairs.",
        "question": "Question",
        "qualification_feedback": "Your test answers",
        "passed": "Test passed",
        "retry": "Try six different examples",
        "failed": "Thank you for your time. The test was not passed; you will not receive "
        "assignments.",
        "admit": "Start the pairs",
        "full": "Places are currently full",
        "full_help": "Thank you for your interest. You can try again later: availability depends "
        "on the reads still needed.",
        "try_again": "Check availability",
        "batch_done": "You’ve completed this group",
        "batch_help": "Press “More pairs” to continue, if more are available, or “Finish the session”.",
        "next_pair": "Next pair",
        "next_pair_help": "Press “More pairs” to get the next one, or “Finish the session”.",
        "more": "More pairs",
        "quality_stop": "Thank you for your contribution",
        "quality_help": "There are no further assignments for this session. Your completed answers "
        "remain saved and count towards your pay under the rules.",
        "closed": "Collection closed, thank you",
        "closed_help": "Collection has closed. Your saved work and payment details are still "
        "available.",
        "surplus": "Thank you: your answer has been preserved, but this read was no longer needed "
        "or available. It does not add pay.",
        "finish_title": "One last step",
        "finish_intro": "These details identify your participation and help arrange payment.",
        "programme": "Degree programme",
        "other": "Other",
        "programme_help": "If you have already graduated in one of these programmes, choose it and write “graduate” as the year of study.",
        "other_programme": "Specify your programme",
        "year": "Year of study",
        "year_placeholder": "E.g. Year 3, additional year, graduate",
        "finish_button": "Confirm and show my code",
        "thanks": "Thank you. Your contribution matters.",
        "final_help": "Keep this code to resume your session and claim payment. Send it privately "
        "to the study’s author through the channel where you received the link, or by email. "
        "Payment is arranged personally at the end of the study, by the method you "
        "prefer.",
        "payable": "Pay to claim",
        "below_min": "You have not reached the minimum of {minimum} pairs, so no payment is due.",
        "review_programme": "Your programme needs review. Answers and payment are on hold until "
        "authorised.",
        "error": "Something went wrong",
        "error_help": "The form expired or some details are invalid. Reopen the page and try "
        "again: saved answers are safe.",
        "bad_code": "Code not recognised. Check the 8 characters and try again.",
        "rate_limit": "Too many attempts. Wait 15 minutes before trying again.",
        "too_large": "The form is too large. Shorten the text and try again.",
        "return": "Return to your session",
        "read_rules": "By starting, you declare that you meet the requirements, accept the rules "
        "and give consent after reading the privacy notice.",
        "enabled_tutorial": "Before starting: a short guide.",
        "enabled_qualification": "There is a 6-pair entry test (at least {pass_count} correct, "
        "with one retry).",
        "enabled_practice": "The first pair, when available, is a practice example with feedback. "
        "It counts towards pay; the others are real pairs.",
        "fee_rule": "Plus a fixed {fee} after {minimum} completed pairs.",
        "pay_rule": "{price} per completed pair. Payment from {minimum} pairs upwards.",
        "enabled_controls": "The work includes unmarked quality controls, which count towards your "
        "pay.",
        "correct_path": "The correct path",
        "no_ai": "Answer on your own, without AI tools or help from other people.",
        "pay_threshold_amount": "At the payment threshold: {amount}.",
        "pay_practice_price": "The practice pair is worth {practice}.",
        "eligibility_note": "Graduates of these programmes can also take part: in the final form, write “graduate” as the year of study.",
        "paid_tasks": "{count} paid pairs completed",
        "real_pairs": "{count} real pairs completed",
        "accrued": "Accrued",
        "payable_from": "Payable from {minimum} pairs upwards",
        "identity_help": "These details identify your participation and help arrange payment.",
        "first_name": "First name",
        "last_name": "Last name",
        "eligibility_declaration": "I declare that I am an adult enrolled at the University of Pisa in one of the listed programmes, or a graduate of one of them from the same university",
        "finish_below_warning": "You have completed {count} of {minimum} paid pairs. If you finish "
        "now, no payment is due. You can close the page instead and resume later with your code.",
        "finish_below_confirm": "I confirm that I want to finish below the threshold, without "
        "claiming payment.",
        "finish_below_action": "Finish below the minimum",
        "resume_work": "Resume work",
        "closed_resume": "Collection has closed. Your saved work and payment details are still "
        "available.",
        "site_stop_exception": "The site has stopped assigning work. Accepted pairs completed in "
        "good faith remain payable even below the threshold.",
        "programme_review": "Your programme needs review. Answers and payment are on hold until "
        "authorised.",
        "next_work": "Continue with the pairs",
        "preview_rate_header": "Planned rate for the paid collection",
        "preview_tasks": "{count} preview pairs completed",
        "collection_coverage": "{percent}% of required reads completed",
        "coverage_complete": "All pairs have the required reads.",
        "coverage_incomplete": "Collection has closed, but some pairs still lack required reads.",
        "coverage_summary": "Pairs with at least two reads: {covered}/{total} · "
        "With a final judgment: {resolved}/{total}",
        "update_details": "Update your details",
        "cannot_tell": "Cannot tell",
        "not_extracted": "Not extracted",
        "not_reported": "Not reported",
    },
}


QUESTIONS = {
    "it": [
        (
            "Il risultato estratto corrisponde all’abstract?",
            "Controlla sette aspetti, prima per A e poi per B.",
            (
                "Un campo vuoto è corretto solo se l’abstract non riporta quell’informazione. Se invece "
                "è nel testo ma manca nell’estrazione, scegli «No»."
            ),
            "Se trovi un problema, indica se cambia il risultato o il confronto.",
        ),
        (
            "I due risultati si possono confrontare?",
            "Controlla esposizione o intervento, esito, misure e confronto.",
            (
                "Popolazioni o metodi diversi possono essere abbastanza confrontabili. Unità convertibili "
                "non impediscono da sole il confronto."
            ),
            "Se manca un’informazione essenziale, scegli «Non posso stabilirlo».",
        ),
        (
            "I due studi riportano lo stesso risultato?",
            "La stessa direzione, oppure un’assenza di differenza dichiarata da entrambi.",
            (
                "Dimensioni diverse dell’effetto possono concordare. La sola differenza di "
                "significatività non indica direzioni opposte."
            ),
            (
                "Una mancata conferma esplicita va alla domanda successiva anche se la stima ha lo stesso "
                "segno."
            ),
        ),
        (
            "In che cosa differiscono i risultati?",
            "Distingui effetto non confermato, direzioni opposte e sola differenza di grandezza.",
            (
                "Un effetto contro un’assenza dichiarata o una mancata conferma viene prima di una "
                "possibile spiegazione di contesto."
            ),
            "Se il testo non basta per decidere, indicalo.",
        ),
        (
            "Gli abstract descrivono una differenza che potrebbe spiegare i risultati opposti?",
            "Confronta ciò che ciascun abstract dice del proprio studio.",
            (
                "Scegli una differenza concreta, pertinente e sostenuta dai testi. Non serve provare che "
                "abbia causato la divergenza."
            ),
            "Se manca un’informazione essenziale, non confonderla con l’assenza di una spiegazione.",
        ),
    ],
    "en": [
        (
            "Does this extracted finding match the abstract?",
            "Check seven things, first for A and then for B.",
            (
                "An empty field is correct only when the abstract does not give that information. If the "
                "abstract gives it but the extraction leaves it out, choose “No”."
            ),
            "If you find a problem, say whether it changes the finding or comparison.",
        ),
        (
            "Can the two findings be compared?",
            "Check exposure or intervention, outcome, measurements and comparison.",
            (
                "Different populations or methods may still be comparable. Convertible units do not by "
                "themselves prevent comparison."
            ),
            "If essential information is missing, choose “Cannot tell”.",
        ),
        (
            "Do both studies report the same finding?",
            "The same direction, or both explicitly report no difference.",
            (
                "Different effect sizes can still agree. A difference in statistical significance alone "
                "is not an opposite finding."
            ),
            (
                "Explicit non-confirmation goes to the next question even when the estimate has the same "
                "direction."
            ),
        ),
        (
            "How do the two studies’ results differ?",
            "Distinguish non-confirmation, opposite directions and differences only in size.",
            (
                "A reported effect against explicit absence or non-confirmation takes priority over a "
                "possible contextual explanation."
            ),
            "If the text is not enough to decide, say so.",
        ),
        (
            "Do the abstracts describe a difference that could explain the opposite findings?",
            "Compare what each abstract says about its own study.",
            (
                "Choose a concrete, relevant difference supported by the texts. You do not need to prove "
                "it caused the difference in findings."
            ),
            "Missing essential information is not the same as having no explanation.",
        ),
    ],
}


# Presentation-only labels; the scientific instrument wording stays at version 2.0.
UI["en"].update(
    {
        "check_progress": "Check {current} of {total}, abstract {side}",
        "comparison_progress": "Check {current} of {total}",
        "change_check": "Change",
        "active_finding": "What the system extracted · abstract {side}",
        "source_section": "See in abstract {side}",
        "return_check": "Back to the check",
    }
)
UI["it"].update(
    {
        "check_progress": "Controllo {current} di {total}, abstract {side}",
        "comparison_progress": "Controllo {current} di {total}",
        "change_check": "Modifica",
        "active_finding": "Quello che il sistema ha estratto · abstract {side}",
        "source_section": "Vedi nell’abstract {side}",
        "return_check": "Torna al controllo",
    }
)


UI["it"].update(
    {
        "study_percent": "Studio completo {al}{percent}%",
        "study_early": "Sii tra i primi",
        "study_help": "Aiutaci a completarlo",
        "study_almost": "Manca poco",
        "about_author": "Chi conduce lo studio",
        "source_code": "Codice sorgente",
        "contact": "Un dubbio? Scrivi a",
        "sheet_toggle": "Apri o riduci la domanda",
        "leave_comment": "Lascia un commento",
        "draft_short": "Bozza salvata su questo dispositivo.",
        "reading": "Lettura",
        "instructions": "Istruzioni",
        "session_details": "La tua sessione",
        "show_abstract": "Abstract {side}",
        "current_context": "Dati estratti",
    }
)
UI["en"].update(
    {
        "study_percent": "Study {percent}% complete",
        "study_early": "Be one of the first",
        "study_help": "Help us complete it",
        "study_almost": "Almost there",
        "about_author": "Who runs this study",
        "source_code": "Source code",
        "contact": "Questions? Write to",
        "sheet_toggle": "Expand or collapse the question",
        "leave_comment": "Leave a comment",
        "draft_short": "Draft saved on this device.",
        "reading": "Reading",
        "instructions": "Instructions",
        "session_details": "Your session",
        "show_abstract": "Abstract {side}",
        "current_context": "Extracted details",
    }
)


UI["it"].update(
    {
        "practice": "Coppia di prova",
        "practice_label": "Coppia di prova · esempio inventato, con spiegazioni",
        "practice_intro_title": "Coppia di prova",
        "practice_intro_one": "È un esempio inventato per imparare come funziona il compito.",
        "practice_intro_two": "Leggi due brevi abstract, controlla se i risultati estratti dal sistema corrispondono ai testi, poi valuta se i risultati si possono confrontare e se sono in disaccordo.",
        "practice_intro_rule": "Per ogni riga scegli «No» se un campo è sbagliato, impreciso o incompleto, oppure se è «Non estratto» o «Non riportato» ma l’abstract riporta quell’informazione.",
        "practice_intro_three": "Dopo l’invio delle risposte vedrai una spiegazione.",
        "practice_intro_four": "La prova conta per il compenso, come indicato nelle regole.",
        "practice_begin": "Inizia la prova",
        "preview_task_short": "Anteprima: le risposte non vengono conteggiate né pagate",
        "synthetic_example": "Esempio inventato",
        "view_summary": "Vedi il riassunto",
        "comparison_block": "Confronto",
    }
)
UI["en"].update(
    {
        "practice": "Practice pair",
        "practice_label": "Practice pair · invented example, with explanations",
        "practice_intro_title": "Practice pair",
        "practice_intro_one": "This is an invented example to learn how the task works.",
        "practice_intro_two": "Read two short abstracts, check whether the findings extracted by the system match the texts, then decide whether the findings can be compared and whether they disagree.",
        "practice_intro_rule": "In every row, choose “No” if a field is wrong, imprecise or incomplete, or if it shows “Not extracted” or “Not reported” but the abstract gives that information.",
        "practice_intro_three": "After you submit your answers, you will see an explanation.",
        "practice_intro_four": "The practice counts towards pay, as described in the rules.",
        "practice_begin": "Start the practice",
        "preview_task_short": "Preview: answers are not counted or paid",
        "synthetic_example": "Invented example",
        "view_summary": "View the summary",
        "comparison_block": "Comparison",
    }
)


# Corrections of submitted pairs. {when} is a full phrase from
# corrections.when: «il 14 novembre 2026 alle 15:42» / "on 14 November 2026 at 15:42".
UI["it"].update(
    {
        "submitted_link": "Rivedi le coppie consegnate",
        "submitted_title": "Le coppie che hai consegnato",
        "submitted_intro": "Se ti accorgi di un errore, puoi correggere la risposta a una coppia "
        "già consegnata. La risposta originale resta registrata; il compenso non cambia.",
        "submitted_empty": "Non hai ancora consegnato coppie reali. La coppia di prova non "
        "compare in questo elenco.",
        "submitted_pair": "Coppia {number}",
        "submitted_at": "Consegnata {when}",
        "corrected_at": "Corretta {when}",
        "review_and_correct": "Rivedi e correggi",
        "correction_saved": "Correzione salvata: coppia {number}.",
        "correction_saved_plain": "Correzione salvata.",
        "correction_unchanged": "Nessuna modifica rispetto all’ultima versione: non è stato "
        "registrato nulla.",
        "correction_rate_limit": "Troppi salvataggi in poco tempo. Attendi 15 minuti prima di "
        "salvare un’altra correzione: questa non è stata registrata.",
        "correction_closed": "La raccolta è chiusa: le coppie consegnate restano visibili, ma "
        "non si possono più correggere.",
        "correction_label": "Correzione · Coppia {number}",
        "correction_banner": "Stai correggendo una risposta consegnata {when}. La risposta "
        "originale resta registrata; il compenso non cambia.",
        "correction_from_original": "Le scelte sono quelle che hai consegnato: cambia solo ciò "
        "che vuoi correggere.",
        "correction_from_latest": "Le scelte sono quelle della tua ultima correzione, salvata "
        "{when}: cambia solo ciò che vuoi correggere.",
        "correction_review_final": "Salvando, questa diventa la tua risposta per la coppia. La "
        "risposta originale resta registrata.",
        "correction_save": "Salva la correzione",
        "correction_cancel": "Torna all’elenco senza modificare",
        "correction_caption": "La correzione è registrata solo quando premi «Salva la correzione».",
    }
)
UI["en"].update(
    {
        "submitted_link": "Review the pairs you submitted",
        "submitted_title": "The pairs you submitted",
        "submitted_intro": "If you notice a mistake, you can correct your answer to a pair you "
        "have already submitted. The original answer stays recorded; your pay does not change.",
        "submitted_empty": "You have not submitted any real pairs yet. The practice pair is not "
        "listed here.",
        "submitted_pair": "Pair {number}",
        "submitted_at": "Submitted {when}",
        "corrected_at": "Corrected {when}",
        "review_and_correct": "Review and correct",
        "correction_saved": "Correction saved: pair {number}.",
        "correction_saved_plain": "Correction saved.",
        "correction_unchanged": "No changes from the latest version: nothing was recorded.",
        "correction_rate_limit": "Too many saves in a short time. Wait 15 minutes before saving "
        "another correction: this one was not recorded.",
        "correction_closed": "Collection has closed: your submitted pairs stay visible, but can "
        "no longer be corrected.",
        "correction_label": "Correction · Pair {number}",
        "correction_banner": "You are correcting an answer submitted {when}. The original answer "
        "stays recorded; your pay does not change.",
        "correction_from_original": "The choices are the ones you submitted: change only what "
        "you want to correct.",
        "correction_from_latest": "The choices are those of your latest correction, saved "
        "{when}: change only what you want to correct.",
        "correction_review_final": "When you save, this becomes your answer for the pair. The "
        "original answer stays recorded.",
        "correction_save": "Save the correction",
        "correction_cancel": "Back to the list without changes",
        "correction_caption": "The correction is recorded only when you press “Save the "
        "correction”.",
    }
)


PLURALS = {
    "it": {
        "paid_tasks": (
            "count",
            "{count} coppia retribuita completata",
            "{count} coppie retribuite completate",
        ),
        "real_pairs": (
            "count",
            "{count} coppia reale completata",
            "{count} coppie reali completate",
        ),
        "preview_tasks": (
            "count",
            "{count} coppia di prova completata",
            "{count} coppie di prova completate",
        ),
        "done": ("count", "coppia completata", "coppie completate"),
        "enabled_qualification": (
            "pass_count",
            "È prevista una prova iniziale di 6 coppie (almeno {pass_count} corretta, un secondo tentativo).",
            "È prevista una prova iniziale di 6 coppie (almeno {pass_count} corrette, un secondo tentativo).",
        ),
        "qualification_intro": (
            "pass_count",
            "Sei brevi esempi inventati. Serve {pass_count} risposta corretta per continuare. Hai due tentativi; questa prova non conta come coppia retribuita.",
            "Sei brevi esempi inventati. Servono {pass_count} risposte corrette per continuare. Hai due tentativi; questa prova non conta come coppia retribuita.",
        ),
        "payline": (
            "minimum",
            "{price} per coppia completata · pagamento da {minimum} coppia in su.",
            "{price} per coppia completata · pagamento da {minimum} coppie in su.",
        ),
        "payable_from": (
            "minimum",
            "Pagamento da {minimum} coppia in su",
            "Pagamento da {minimum} coppie in su",
        ),
        "minimum": (
            "minimum",
            "Pagamento da {minimum} coppia in su",
            "Pagamento da {minimum} coppie in su",
        ),
        "fee_rule": (
            "minimum",
            "In più, {fee} fissi dopo {minimum} coppia completata.",
            "In più, {fee} fissi dopo {minimum} coppie completate.",
        ),
        "finish_below_warning": (
            "count",
            (
                "Hai completato {count} coppia retribuita su {minimum}. Se "
                "termini ora, non è previsto un pagamento. Puoi invece chiudere la "
                "pagina e riprendere più tardi con il tuo codice."
            ),
            (
                "Hai completato {count} coppie retribuite su {minimum}. Se "
                "termini ora, non è previsto un pagamento. Puoi invece chiudere la "
                "pagina e riprendere più tardi con il tuo codice."
            ),
        ),
    },
    "en": {
        "paid_tasks": ("count", "{count} paid pair completed", "{count} paid pairs completed"),
        "real_pairs": ("count", "{count} real pair completed", "{count} real pairs completed"),
        "preview_tasks": (
            "count",
            "{count} preview pair completed",
            "{count} preview pairs completed",
        ),
        "done": ("count", "pair completed", "pairs completed"),
        "qualification_intro": (
            "pass_count",
            "Six short invented examples. You need {pass_count} correct answer to continue. You have two attempts; this test does not count as paid pairs.",
            "Six short invented examples. You need {pass_count} correct answers to continue. You have two attempts; this test does not count as paid pairs.",
        ),
        "payable_from": (
            "minimum",
            "Payable from {minimum} pair upwards",
            "Payable from {minimum} pairs upwards",
        ),
        "minimum": (
            "minimum",
            "Payable from {minimum} pair upwards",
            "Payable from {minimum} pairs upwards",
        ),
        "fixed_progress": (
            "minimum",
            "Fixed fee: {fee} from {minimum} pair",
            "Fixed fee: {fee} from {minimum} pairs",
        ),
        "fee_rule": (
            "minimum",
            "Plus a fixed {fee} after {minimum} completed pair.",
            "Plus a fixed {fee} after {minimum} completed pairs.",
        ),
        "payline": (
            "minimum",
            "{price} per completed pair · payment from {minimum} pair upwards.",
            "{price} per completed pair · payment from {minimum} pairs upwards.",
        ),
        "pay_rule": (
            "minimum",
            "{price} per completed pair. Payment from {minimum} pair upwards.",
            "{price} per completed pair. Payment from {minimum} pairs upwards.",
        ),
        "below_min": (
            "minimum",
            "You have not reached the minimum of {minimum} pair, so no payment is due.",
            "You have not reached the minimum of {minimum} pairs, so no payment is due.",
        ),
        "finish_below_warning": (
            "minimum",
            (
                "You have completed {count} of {minimum} paid pair. If you finish "
                "now, no payment is due. You can close the page instead and resume later with your code."
            ),
            (
                "You have completed {count} of {minimum} paid pairs. If you "
                "finish now, no payment is due. You can close the page instead "
                "and resume later with your code."
            ),
        ),
    },
}


def italian_al(number):
    """Return «al », «allo » or «all’» as spoken before an integer percentage."""
    n = int(number)
    if n == 0:
        return "allo "
    if n in (1, 8, 11) or 80 <= n <= 89:
        return "all’"
    return "al "


def translate(lang, key, **kwargs):
    """Format UI text, choosing singular/plural from its actual count."""
    text = UI[lang].get(key, key)
    choice = PLURALS[lang].get(key)
    if choice and choice[0] in kwargs:
        text = choice[1] if kwargs[choice[0]] == 1 else choice[2]
    if "{al}" in text and "percent" in kwargs:
        kwargs = {**kwargs, "al": italian_al(kwargs["percent"])}
    return text.format(**kwargs)


# Variants for an instance without compensation (COMPENSATION_ENABLED=false). The app
# uses "<key>_nopay" instead of "<key>" whenever the variant exists.
UI["it"].update(
    {
        "rules_nopay": "Regole",
        "closed_resume_nopay": "La raccolta è chiusa. Le risposte salvate restano registrate.",
        "code_help_nopay": "Conserva il codice per riprendere la sessione.",
        "correction_banner_nopay": "Stai correggendo una risposta consegnata {when}. "
        "La risposta originale resta registrata.",
        "enabled_controls_nopay": "Durante il lavoro sono previsti controlli di qualità non "
        "segnalati.",
        "enabled_practice_nopay": "La prima coppia, quando disponibile, è una prova con una "
        "spiegazione; le altre sono coppie reali.",
        "excluded_programmes_nopay": "Le risposte di chi non ha questi requisiti non vengono "
        "usate.",
        "final_help_nopay": "Conserva il codice per riprendere la sessione.",
        "identity_help_nopay": "Questi dati descrivono chi partecipa e servono a verificare i "
        "requisiti dello studio.",
        "practice_intro_four_nopay": "La prova serve solo a imparare il compito.",
        "preview_banner_nopay": "Anteprima: le risposte non vengono conteggiate",
        "preview_task_short_nopay": "Anteprima: le risposte non vengono conteggiate",
        "programme_review_nopay": "Hai indicato un corso da verificare. Le risposte restano "
        "sospese in attesa di autorizzazione.",
        "site_stop_exception_nopay": "Il sito ha interrotto le assegnazioni. Le risposte "
        "consegnate restano registrate.",
        "submitted_intro_nopay": "Se ti accorgi di un errore, puoi correggere la risposta a "
        "una coppia già consegnata. La risposta originale resta registrata.",
    }
)
UI["en"].update(
    {
        "rules_nopay": "Rules",
        "closed_resume_nopay": "Collection has closed. Your saved work is still recorded.",
        "code_help_nopay": "Keep this code to resume your session.",
        "correction_banner_nopay": "You are correcting an answer submitted {when}. "
        "The original answer stays recorded.",
        "enabled_controls_nopay": "The work includes unmarked quality controls.",
        "enabled_practice_nopay": "The first pair, when available, is a practice example with "
        "feedback; the others are real pairs.",
        "excluded_programmes_nopay": "Answers from people who do not meet these requirements "
        "are not used.",
        "final_help_nopay": "Keep this code to resume your session.",
        "identity_help_nopay": "These details describe who takes part and are used to check "
        "the study's requirements.",
        "practice_intro_four_nopay": "The practice is only for learning the task.",
        "preview_banner_nopay": "Preview: answers are not counted",
        "preview_task_short_nopay": "Preview: answers are not counted",
        "programme_review_nopay": "Your programme needs review. Answers are on hold until "
        "authorised.",
        "site_stop_exception_nopay": "The site has stopped assigning work. Your submitted "
        "answers stay recorded.",
        "submitted_intro_nopay": "If you notice a mistake, you can correct your answer to a "
        "pair you have already submitted. The original answer stays recorded.",
    }
)


DECISION_PATHS = {}
