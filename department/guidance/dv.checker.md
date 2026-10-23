# Checker/Assertion

- SPEC 요구사항을 프로토콜 체커와 SVA assertion으로 쓴다.
- 파이프라인 Verifier 산출물은 볼 수 없다. SPEC과 L1만 근거로 쓴다.
- SVA는 Verilator `--assert`로 실행해야 돈다 (P8 DV 공백 "SVA 미실행"). 실패 동작은 `$display("[SVA] FAIL ...")`로 내고 `$error`나 `$stop`은 쓰지 않는다 (시뮬레이션이 멈춰 남은 테스트까지 실패로 보임). 일부러 틀린 assertion 하나로 실제로 걸리는지 먼저 확인한다. 예: `experiments/p8/crc_dv/`.
