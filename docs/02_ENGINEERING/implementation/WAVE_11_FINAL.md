# Wave 11 Finalization Plan

Status: plan for completing Wave 11 after first real-LLM testing.

## Block 1. Fix Known Issues

1. Fix `accepted + issues`: validator must not pass text into `approved_texts` if LLM returned any validation issues.

2. Fix Chukovsky style detection: request with "в стиле Чуковского" must be represented in state/prompt context as a supported reference/style label.

3. Fix truth mode: requests for "правдивые истории" must keep `TRUTH`, and Stage 2 must not turn them into fairy tales.

4. Fix basic real LLM happy path: a simple request with age and subject must produce usable `approved_texts`, not `0/2`.

## Block 2. Run Detailed Manual Tests

Run a series of manual LLM tests across key scenarios and record for each:

- request;
- session_id;
- final status;
- approved_count;
- what state detected correctly/incorrectly;
- where behavior broke if unexpected;
- what issues need fixing based on the result.

Put the actual requests in the appendix below.

## Block 3. Record Business Logic Checks

Do not fix these now. Record them for future decision/checking:

1. `approved_texts` length: current final text length is unconstrained. Define length rules by age/format and decide what to do with overlength.

2. Cross-session diversity: diversity between different sessions is not specified. Decide whether it is required for MVP.

3. Missing age behavior: missing age may currently default to `5`. Confirm whether this is desired or should trigger clarification.

## Appendix. Manual Test Requests

1. `Сделай 2 сказки про лису для 5 лет`

2. `Сделай 2 правдивые истории про лису для 5 лет`

3. `Сделай 2 сказки про лису`

4. `2 сказки`

5. `Сделай сказку про лису для 5 лет в стиле Чуковского`

6. `Сделай сказку про лису для 5 лет строго в стиле Дисней`

7. `Сделай сказку про лису для 5 лет в акварельном настроении`

8. `Сделай правдивую историю про лису для 5 лет, обязательно чтобы она летала на волшебном ковре`

9. `Сделай 2 поучительные сказки про лису и переход через дорогу для 5 лет`

10. `Сделай поучительную историю про незнакомца и конфету для ребёнка 5 лет`

11. `Сделай 3 истории про лису, зайца и белку зимой, чтобы герои не исчезали`

12. `Сделай историю про бельчонка Тима, он смелый и любит жёлуди, для 5 лет`

13. `Сделай правдивую историю про попугая какаду для 5 лет`

14. `Сделай мягкую мифологическую историю про солнце и ветер для ребёнка 5 лет`

15. `Сделай 2 сказки про лису для 5 лет` - run 3 times and compare diversity.
