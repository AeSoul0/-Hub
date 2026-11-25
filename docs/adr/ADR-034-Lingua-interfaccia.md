# ADR-034: Lingua dell'interfaccia, lingua della voce e contesto dell'app

## Status
**Accepted** (2026-11-25, richiesta dell'utente: frontend in inglese con la scelta tra inglese e italiano; la lingua delle voci dipende dalla voce scelta; un avviso quando voce e interfaccia hanno lingue diverse, con "non mostrare più", riattivabile da Impostazioni o chiedendolo ad Aurora; Aurora cambia anche la lingua e conosce l'app)

## Context
- **Il frontend era tutto in italiano,** scritto direttamente nel codice delle pagine.
- **La voce ha già la sua lingua.** La voce Piper la porta nel nome (`it_IT-paola-medium`). Una voce ElevenLabs può dichiararla tra le sue etichette.
- **Aurora non sapeva niente dell'app.** Il prompt del worker era un contratto fisso, senza la lingua delle pagine, la voce o le pagine stesse. Quindi non poteva rispondere "come si cambia la lingua?" e non poteva cambiarla.

## Decision
1. **Due impostazioni del backend, non del browser,** così Impostazioni e Aurora cambiano la stessa cosa:
   - `AEHUB_UI_LANGUAGE`: `en` (predefinita) o `it`;
   - `AEHUB_VOICE_LANGUAGE_WARNING`: `on` (predefinita) o `off`.

   Si salvano con `PUT /api/settings` e finiscono nella catena dell'audit come ogni impostazione.
2. **`GET /api/interface`** restituisce:
   - la lingua;
   - l'avviso, acceso o spento;
   - la voce: accesa o no, motore, nome e lingua.

   **La lingua della voce segue la voce scelta:**
   - per Piper, il prefisso del nome (`it_IT-…` → `it`);
   - per ElevenLabs, l'etichetta `language` dell'ultimo elenco delle voci;
   - altrimenti è sconosciuta, e l'avviso non compare.
3. **Ogni pagina cambia subito.**
   - Il componente `InterfaceProvider` (layout radice) legge `/api/interface`:
     - all'avvio;
     - dopo l'accesso;
     - quando la finestra torna in primo piano;
     - all'evento `interface.changed`, che il backend manda quando cambiano lingua, voce o avviso, da Impostazioni o da Aurora.
   - Il browser tiene una copia della lingua (`aehub.language`) solo per dipingere la prima schermata nella lingua giusta.
4. **I testi stanno accanto al codice, in cataloghi** `catalog({ en: {...}, it: {...} })` (`lib/i18n.tsx`).
   - TypeScript vuole che l'italiano abbia la stessa forma dell'inglese, quindi una traduzione mancante è un errore di compilazione.
   - Le funzioni pure (date, dimensioni, stati delle run) ricevono la lingua come argomento.
   - Una lingua in più vuol dire un blocco in più per ogni catalogo e una voce in `LANGS`.
   - **Testi del backend:** restano in inglese, come i log. In italiano le pagine li traducono dove c'erano già le tabelle: problemi della configurazione (ora con i loro valori in `params`), errori di import, memoria, documenti e casa.
5. **L'avviso sulla lingua della voce** compare quando:
   - l'avviso è acceso;
   - la voce è accesa;
   - la lingua della voce è nota;
   - questa lingua è diversa da quella dell'interfaccia.

   Ha **OK** e **Non mostrare più**:
   - **OK** lo chiude per questa sessione del browser, per quella coppia di lingue;
   - **Non mostrare più** salva `AEHUB_VOICE_LANGUAGE_WARNING=off`.

   Lo riattivano Impostazioni → Lingua oppure Aurora.
6. **La voce resta della voce.**
   - Le risposte lette ad alta voce sono nella lingua della voce scelta.
   - La frase di prova nella pagina Voce è nella lingua della voce, non in quella dell'interfaccia.
   - Il riconoscimento vocale resta un'impostazione a parte (`AEHUB_STT_LANGUAGE`).
7. **Aurora conosce l'app e la cambia.**
   - **Contesto:** il worker riceve a ogni turno, dopo il suo contratto, un contesto breve (`core/interface.app_context`):
     - che app è;
     - le pagine;
     - la lingua dell'interfaccia;
     - la lingua della voce;
     - lo stato dell'avviso;
     - i tool per cambiarli.

     Sono solo impostazioni, mai testo dell'utente. È tenuto corto perché si paga a ogni turno: le eval salgono di circa il 5% del costo medio, dentro il gate.
   - **Tool:** la skill `interface` ha `set_interface_language(language)` e `set_voice_language_warning(enabled)`.
     - Sono a rischio basso: niente esce dal computer e si annulla allo stesso modo.
     - Passano dal Tool Gateway.
     - Salvano con `settings_service`, con audit, a nome del principal della run.
     - Mandano `interface.changed`.

## Consequences
- **Nuova installazione:** l'interfaccia è in inglese e la voce predefinita resta `it_IT-paola-medium`. L'avviso quindi compare finché non si sceglie una voce inglese, si passa all'italiano o si sceglie "Non mostrare più".
- **Test del frontend:**
  - i test esistenti girano in italiano (`chooseLanguage("it")`);
  - `tests/interface.test.tsx` copre:
    - l'inglese predefinito;
    - il cambio da Impostazioni;
    - la lingua dal backend;
    - l'evento di Aurora;
    - l'avviso;
    - la lingua della voce.
- **Test del backend:** `tests/agent_engine/test_interface.py` fa una run vera in cui Aurora cambia lingua e avviso, con audit ed evento.
- Lo smoke test nel browser segue l'interfaccia inglese.
- Il test del budget di contesto (`test_context_rag`) passa da 12.000 a 12.500 token: L0 ora contiene anche il contesto dell'app.

## Alternatives considered
- **Lingua solo nel browser (localStorage):** più semplice, ma Aurora non potrebbe cambiarla né conoscerla.
- **Una libreria i18n con chiavi** (next-intl, i18next): chiavi lontane dal codice e nessun controllo di completezza senza strumenti in più. I cataloghi tipati bastano per due lingue e reggono una terza.
- **Una lingua delle risposte legata all'interfaccia:** l'utente ha chiesto che la voce segua la voce scelta. Aurora risponde nella lingua in cui le si scrive.
