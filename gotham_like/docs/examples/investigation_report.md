# Investigation Report — Demo: accounts, devices, transactions and locations

**SYNTHETIC / DEMONSTRATION DATA**

_This report supports human decision-making. It does not make determinations about any person or organisation._

Generated 2026-09-26T10:21:41.179732+00:00 by investigator

## Investigation Summary

Analyze relationships between accounts, devices, transactions and locations around device DV-7F3A-SHARED (synthetic data).

- entities: 11
- relationships: 106
- events: 166
- signals: 18
- assertions: 1
- evidence_items: 15

## Scope

- area: 2 km around Harbor Plaza
- question: Which entities connect to DV-7F3A-SHARED in March 2026, and how?
- time_window: ['2026-03-01', '2026-03-31']

## Entities

| Type | Label | Confidence | Status | Sources |
|---|---|---|---|---|
| Account | 8777794369 | 1.00 | DERIVED | 25 |
| Account | 4577796341 | 1.00 | DERIVED | 18 |
| Account | 3020546666 | 1.00 | DERIVED | 23 |
| Account | 6834741794 | 1.00 | DERIVED | 22 |
| Account | 4504455827 | 1.00 | DERIVED | 39 |
| Account | 1828289951 | 1.00 | DERIVED | 29 |
| Account | 2658356974 | 1.00 | DERIVED | 25 |
| Account | 3703750755 | 1.00 | DERIVED | 20 |
| Device | DV-7F3A-SHARED | 1.00 | DERIVED | 43 |
| Domain | update-portal.example | 1.00 | DERIVED | 8 |
| IPAddress | 203.0.113.66 | 1.00 | DERIVED | 64 |

## Relationships

| Source | Type | Target | Time | Confidence | Status | Source records |
|---|---|---|---|---|---|---|
| acco_f301da0a0714182a581f | USED | devi_c54142cba994ccc51e36 | 2026-03-01T00:00:00+00:00 | 1.00 | DERIVED | src_962e9d045844d650c0ff |
| acco_84ecb411751ea1d44862 | USED | devi_c54142cba994ccc51e36 | 2026-03-04T01:00:00+00:00 | 1.00 | DERIVED | src_b5355d9adc26498b6494 |
| acco_60975226572ab6686444 | USED | devi_c54142cba994ccc51e36 | 2026-03-07T02:00:00+00:00 | 1.00 | DERIVED | src_e45f4f56326a26b7fcda |
| acco_7235733e5885cd1f6b4d | USED | devi_c54142cba994ccc51e36 | 2026-03-10T03:00:00+00:00 | 1.00 | DERIVED | src_93425fae363ed508a26d |
| acco_6e4c16b95325d7ce074a | USED | devi_c54142cba994ccc51e36 | 2026-03-13T04:00:00+00:00 | 1.00 | DERIVED | src_c9d88a6c5f9f403f67fb |
| acco_f13b45e86b1a54f40bc5 | USED | devi_c54142cba994ccc51e36 | 2026-03-16T05:00:00+00:00 | 1.00 | DERIVED | src_1bcac8678aacf967a30a |
| acco_0993876138d30b18428c | USED | devi_c54142cba994ccc51e36 | 2026-03-19T06:00:00+00:00 | 1.00 | DERIVED | src_d24065db1d4a564c1b27 |
| acco_f301da0a0714182a581f | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-01T02:00:00+00:00 | 1.00 | DERIVED | src_67cc885c67fdbd987b66 |
| acco_f301da0a0714182a581f | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-02T02:00:00+00:00 | 1.00 | DERIVED | src_81106f993d2c37b2b94a |
| acco_f301da0a0714182a581f | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-03T02:00:00+00:00 | 1.00 | DERIVED | src_4efc43aeefceb326d2bd |
| acco_f301da0a0714182a581f | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-04T02:00:00+00:00 | 1.00 | DERIVED | src_d8f39dc24202b47bfb4b |
| acco_84ecb411751ea1d44862 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-04T02:00:00+00:00 | 1.00 | DERIVED | src_83a3fcbce4f8a5955784 |
| acco_84ecb411751ea1d44862 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-05T02:00:00+00:00 | 1.00 | DERIVED | src_273aad870051c0fe7a4b |
| acco_84ecb411751ea1d44862 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-06T02:00:00+00:00 | 1.00 | DERIVED | src_45c408432fcf8dd09a36 |
| acco_84ecb411751ea1d44862 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-07T02:00:00+00:00 | 1.00 | DERIVED | src_a8f1d7cdb3470939a311 |
| acco_60975226572ab6686444 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-07T02:00:00+00:00 | 1.00 | DERIVED | src_63ac1d20aa330694a8cd |
| acco_60975226572ab6686444 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-08T02:00:00+00:00 | 1.00 | DERIVED | src_90bc51d52bc3a5d9df97 |
| acco_60975226572ab6686444 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-09T02:00:00+00:00 | 1.00 | DERIVED | src_3a6c941a45aa9d261bb8 |
| acco_60975226572ab6686444 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-10T02:00:00+00:00 | 1.00 | DERIVED | src_2fafd217ca4c4baff4a2 |
| acco_7235733e5885cd1f6b4d | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-10T02:00:00+00:00 | 1.00 | DERIVED | src_33a3c6ebd53dbca83bd4 |
| acco_7235733e5885cd1f6b4d | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-11T02:00:00+00:00 | 1.00 | DERIVED | src_68a4c7e4180dd79c36e0 |
| acco_7235733e5885cd1f6b4d | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-12T02:00:00+00:00 | 1.00 | DERIVED | src_a0f424d6d6e47be9906a |
| acco_7235733e5885cd1f6b4d | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-13T02:00:00+00:00 | 1.00 | DERIVED | src_63426b6a8779d677303a |
| acco_6e4c16b95325d7ce074a | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-13T02:00:00+00:00 | 1.00 | DERIVED | src_ee6af372435c9c90fe77 |
| acco_6e4c16b95325d7ce074a | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-14T02:00:00+00:00 | 1.00 | DERIVED | src_8c809f47536431365bb1 |
| acco_6e4c16b95325d7ce074a | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-15T02:00:00+00:00 | 1.00 | DERIVED | src_32ba37627ff4830ce072 |
| acco_6e4c16b95325d7ce074a | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-16T02:00:00+00:00 | 1.00 | DERIVED | src_d8c92e750227dc47eaad |
| acco_f13b45e86b1a54f40bc5 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-16T02:00:00+00:00 | 1.00 | DERIVED | src_152563a4f945ceff7c4d |
| acco_f13b45e86b1a54f40bc5 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-17T02:00:00+00:00 | 1.00 | DERIVED | src_f15fbb00632da10563ee |
| acco_f13b45e86b1a54f40bc5 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-18T02:00:00+00:00 | 1.00 | DERIVED | src_a55c0fed4f64097825c8 |
| acco_f13b45e86b1a54f40bc5 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-19T02:00:00+00:00 | 1.00 | DERIVED | src_61395734672f848db052 |
| acco_0993876138d30b18428c | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-19T02:00:00+00:00 | 1.00 | DERIVED | src_337a4924100538ab96e0 |
| acco_0993876138d30b18428c | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-20T02:00:00+00:00 | 1.00 | DERIVED | src_f91db30b89896d7b8d36 |
| acco_0993876138d30b18428c | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-21T02:00:00+00:00 | 1.00 | DERIVED | src_5efe2b3ee551d6ee134d |
| acco_0993876138d30b18428c | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-22T02:00:00+00:00 | 1.00 | DERIVED | src_74c051105cb38c9194f0 |
| acco_f301da0a0714182a581f | USED | devi_c54142cba994ccc51e36 | 2026-03-01T01:18:00+00:00 | 1.00 | DERIVED | src_751a5d84a96eb52ec9b7 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-01T01:18:00+00:00 | 1.00 | DERIVED | src_751a5d84a96eb52ec9b7 |
| acco_f301da0a0714182a581f | USED | devi_c54142cba994ccc51e36 | 2026-03-01T01:30:00+00:00 | 1.00 | DERIVED | src_be4f05009508fd0df100 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-01T01:30:00+00:00 | 1.00 | DERIVED | src_be4f05009508fd0df100 |
| acco_f301da0a0714182a581f | USED | devi_c54142cba994ccc51e36 | 2026-03-01T01:42:00+00:00 | 1.00 | DERIVED | src_67d0943443a1ad0421e0 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-01T01:42:00+00:00 | 1.00 | DERIVED | src_67d0943443a1ad0421e0 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-01T01:44:00+00:00 | 1.00 | DERIVED | src_f0723e6527311636dd60 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | doma_2d8a76f40a7ab0d2d148 | 2026-03-01T01:44:00+00:00 | 1.00 | DERIVED | src_f0723e6527311636dd60 |
| acco_f301da0a0714182a581f | USED | devi_c54142cba994ccc51e36 | 2026-03-01T02:10:00+00:00 | 1.00 | DERIVED | src_7d18da7a7e3a060a5c49 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-01T02:10:00+00:00 | 1.00 | DERIVED | src_7d18da7a7e3a060a5c49 |
| acco_84ecb411751ea1d44862 | USED | devi_c54142cba994ccc51e36 | 2026-03-04T01:18:00+00:00 | 1.00 | DERIVED | src_56b834685d89951a58dc |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-04T01:18:00+00:00 | 1.00 | DERIVED | src_56b834685d89951a58dc |
| acco_84ecb411751ea1d44862 | USED | devi_c54142cba994ccc51e36 | 2026-03-04T01:30:00+00:00 | 1.00 | DERIVED | src_05ffda17a5d3984af61a |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-04T01:30:00+00:00 | 1.00 | DERIVED | src_05ffda17a5d3984af61a |
| acco_84ecb411751ea1d44862 | USED | devi_c54142cba994ccc51e36 | 2026-03-04T01:42:00+00:00 | 1.00 | DERIVED | src_8a9ea7ae489efb20bce9 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-04T01:42:00+00:00 | 1.00 | DERIVED | src_8a9ea7ae489efb20bce9 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-04T01:44:00+00:00 | 1.00 | DERIVED | src_300b3161c98b4b6101a9 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | doma_2d8a76f40a7ab0d2d148 | 2026-03-04T01:44:00+00:00 | 1.00 | DERIVED | src_300b3161c98b4b6101a9 |
| acco_84ecb411751ea1d44862 | USED | devi_c54142cba994ccc51e36 | 2026-03-04T02:10:00+00:00 | 1.00 | DERIVED | src_711a733c59b95ac6828b |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-04T02:10:00+00:00 | 1.00 | DERIVED | src_711a733c59b95ac6828b |
| acco_60975226572ab6686444 | USED | devi_c54142cba994ccc51e36 | 2026-03-07T01:18:00+00:00 | 1.00 | DERIVED | src_0151b957015450c417a1 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-07T01:18:00+00:00 | 1.00 | DERIVED | src_0151b957015450c417a1 |
| acco_60975226572ab6686444 | USED | devi_c54142cba994ccc51e36 | 2026-03-07T01:30:00+00:00 | 1.00 | DERIVED | src_a2542227db8d41d193ee |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-07T01:30:00+00:00 | 1.00 | DERIVED | src_a2542227db8d41d193ee |
| acco_60975226572ab6686444 | USED | devi_c54142cba994ccc51e36 | 2026-03-07T01:42:00+00:00 | 1.00 | DERIVED | src_b5919275b9a0b4c35015 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-07T01:42:00+00:00 | 1.00 | DERIVED | src_b5919275b9a0b4c35015 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-07T01:44:00+00:00 | 1.00 | DERIVED | src_b107c592f70288986607 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | doma_2d8a76f40a7ab0d2d148 | 2026-03-07T01:44:00+00:00 | 1.00 | DERIVED | src_b107c592f70288986607 |
| acco_60975226572ab6686444 | USED | devi_c54142cba994ccc51e36 | 2026-03-07T02:10:00+00:00 | 1.00 | DERIVED | src_ef1f6644c951bfd4f49f |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-07T02:10:00+00:00 | 1.00 | DERIVED | src_ef1f6644c951bfd4f49f |
| acco_7235733e5885cd1f6b4d | USED | devi_c54142cba994ccc51e36 | 2026-03-10T01:18:00+00:00 | 1.00 | DERIVED | src_2bbcf0068d9e83d1fbbd |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-10T01:18:00+00:00 | 1.00 | DERIVED | src_2bbcf0068d9e83d1fbbd |
| acco_7235733e5885cd1f6b4d | USED | devi_c54142cba994ccc51e36 | 2026-03-10T01:30:00+00:00 | 1.00 | DERIVED | src_80f244de80e4b0b9890d |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-10T01:30:00+00:00 | 1.00 | DERIVED | src_80f244de80e4b0b9890d |
| acco_7235733e5885cd1f6b4d | USED | devi_c54142cba994ccc51e36 | 2026-03-10T01:42:00+00:00 | 1.00 | DERIVED | src_643efaca4b7d2b255ed8 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-10T01:42:00+00:00 | 1.00 | DERIVED | src_643efaca4b7d2b255ed8 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-10T01:44:00+00:00 | 1.00 | DERIVED | src_46be7772d426b86b73dc |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | doma_2d8a76f40a7ab0d2d148 | 2026-03-10T01:44:00+00:00 | 1.00 | DERIVED | src_46be7772d426b86b73dc |
| acco_7235733e5885cd1f6b4d | USED | devi_c54142cba994ccc51e36 | 2026-03-10T02:10:00+00:00 | 1.00 | DERIVED | src_12dd7bd3085f2b1e94ef |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-10T02:10:00+00:00 | 1.00 | DERIVED | src_12dd7bd3085f2b1e94ef |
| acco_6e4c16b95325d7ce074a | USED | devi_c54142cba994ccc51e36 | 2026-03-13T01:18:00+00:00 | 1.00 | DERIVED | src_298e7628cff35a23fb97 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-13T01:18:00+00:00 | 1.00 | DERIVED | src_298e7628cff35a23fb97 |
| acco_6e4c16b95325d7ce074a | USED | devi_c54142cba994ccc51e36 | 2026-03-13T01:30:00+00:00 | 1.00 | DERIVED | src_90d5e1257f718bcd7a05 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-13T01:30:00+00:00 | 1.00 | DERIVED | src_90d5e1257f718bcd7a05 |
| acco_6e4c16b95325d7ce074a | USED | devi_c54142cba994ccc51e36 | 2026-03-13T01:42:00+00:00 | 1.00 | DERIVED | src_25d8edef220130adeb79 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-13T01:42:00+00:00 | 1.00 | DERIVED | src_25d8edef220130adeb79 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-13T01:44:00+00:00 | 1.00 | DERIVED | src_75a7d4a653d4943ee998 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | doma_2d8a76f40a7ab0d2d148 | 2026-03-13T01:44:00+00:00 | 1.00 | DERIVED | src_75a7d4a653d4943ee998 |
| acco_6e4c16b95325d7ce074a | USED | devi_c54142cba994ccc51e36 | 2026-03-13T02:10:00+00:00 | 1.00 | DERIVED | src_96c764f973511c8ac4ec |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-13T02:10:00+00:00 | 1.00 | DERIVED | src_96c764f973511c8ac4ec |
| acco_f13b45e86b1a54f40bc5 | USED | devi_c54142cba994ccc51e36 | 2026-03-16T01:18:00+00:00 | 1.00 | DERIVED | src_977887a894fd19b0ea1e |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-16T01:18:00+00:00 | 1.00 | DERIVED | src_977887a894fd19b0ea1e |
| acco_f13b45e86b1a54f40bc5 | USED | devi_c54142cba994ccc51e36 | 2026-03-16T01:30:00+00:00 | 1.00 | DERIVED | src_82711e1fa0e4da0c6ff9 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-16T01:30:00+00:00 | 1.00 | DERIVED | src_82711e1fa0e4da0c6ff9 |
| acco_f13b45e86b1a54f40bc5 | USED | devi_c54142cba994ccc51e36 | 2026-03-16T01:42:00+00:00 | 1.00 | DERIVED | src_08949e3624c4d57fbdb4 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-16T01:42:00+00:00 | 1.00 | DERIVED | src_08949e3624c4d57fbdb4 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-16T01:44:00+00:00 | 1.00 | DERIVED | src_a203f8c3c344786583fb |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | doma_2d8a76f40a7ab0d2d148 | 2026-03-16T01:44:00+00:00 | 1.00 | DERIVED | src_a203f8c3c344786583fb |
| acco_f13b45e86b1a54f40bc5 | USED | devi_c54142cba994ccc51e36 | 2026-03-16T02:10:00+00:00 | 1.00 | DERIVED | src_52538ba1fb2eb718898f |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-16T02:10:00+00:00 | 1.00 | DERIVED | src_52538ba1fb2eb718898f |
| acco_0993876138d30b18428c | USED | devi_c54142cba994ccc51e36 | 2026-03-19T01:18:00+00:00 | 1.00 | DERIVED | src_2ea7cb57a0933eec1222 |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-19T01:18:00+00:00 | 1.00 | DERIVED | src_2ea7cb57a0933eec1222 |
| acco_0993876138d30b18428c | USED | devi_c54142cba994ccc51e36 | 2026-03-19T01:30:00+00:00 | 1.00 | DERIVED | src_95ef16404dcd6b1aa44e |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-19T01:30:00+00:00 | 1.00 | DERIVED | src_95ef16404dcd6b1aa44e |
| acco_0993876138d30b18428c | USED | devi_c54142cba994ccc51e36 | 2026-03-19T01:42:00+00:00 | 1.00 | DERIVED | src_acdf63d0094563e5becc |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-19T01:42:00+00:00 | 1.00 | DERIVED | src_acdf63d0094563e5becc |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-19T01:44:00+00:00 | 1.00 | DERIVED | src_c6e77266df7baa8ba52a |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | doma_2d8a76f40a7ab0d2d148 | 2026-03-19T01:44:00+00:00 | 1.00 | DERIVED | src_c6e77266df7baa8ba52a |
| acco_0993876138d30b18428c | USED | devi_c54142cba994ccc51e36 | 2026-03-19T02:10:00+00:00 | 1.00 | DERIVED | src_c302e09a972c923b631e |
| devi_c54142cba994ccc51e36 | CONNECTED_TO | ipad_b18172c56cc969123014 | 2026-03-19T02:10:00+00:00 | 1.00 | DERIVED | src_c302e09a972c923b631e |
| doma_2d8a76f40a7ab0d2d148 | RESOLVES_TO | ipad_b18172c56cc969123014 | 2026-02-20T00:00:00+00:00 | 1.00 | DERIVED | src_74a715fab6bc334e4189 |

## Timeline

Span: {'from': '2020-02-15T15:33:18+00:00', 'to': '2026-06-26T15:59:00+00:00'}

- 2020-02-15T15:33:18+00:00 — account_opened (source: synthetic_core_banking)
- 2020-08-17T10:52:57+00:00 — account_opened (source: synthetic_core_banking)
- 2021-03-06T21:49:15+00:00 — account_opened (source: synthetic_core_banking)
- 2021-08-29T18:31:43+00:00 — account_opened (source: synthetic_core_banking)
- 2022-05-10T03:20:47+00:00 — account_opened (source: synthetic_core_banking)
- 2022-12-13T09:44:39+00:00 — account_opened (source: synthetic_core_banking)
- 2024-09-23T11:19:54+00:00 — account_opened (source: synthetic_core_banking)
- 2024-11-26T06:37:20+00:00 — account_opened (source: synthetic_core_banking)
- 2026-01-04T23:00:50+00:00 — transaction (source: synthetic_payments)
- 2026-01-06T00:37:29+00:00 — transaction (source: synthetic_payments)
- 2026-01-06T18:25:41+00:00 — location_change (source: synthetic_activity)
- 2026-01-07T05:58:57+00:00 — transaction (source: synthetic_payments)
- 2026-01-11T17:25:47+00:00 — transaction (source: synthetic_payments)
- 2026-01-12T18:32:08+00:00 — login (source: synthetic_activity)
- 2026-01-14T12:35:32+00:00 — transaction (source: synthetic_payments)
- 2026-01-16T02:36:57+00:00 — transaction (source: synthetic_payments)
- 2026-01-17T06:33:03+00:00 — transaction (source: synthetic_payments)
- 2026-01-17T17:41:50+00:00 — transaction (source: synthetic_payments)
- 2026-01-18T01:46:25+00:00 — transaction (source: synthetic_payments)
- 2026-01-18T02:08:28+00:00 — transaction (source: synthetic_payments)
- 2026-01-21T02:13:20+00:00 — login (source: synthetic_activity)
- 2026-01-22T03:15:48+00:00 — login (source: synthetic_activity)
- 2026-01-23T03:53:48+00:00 — transaction (source: synthetic_payments)
- 2026-01-24T12:18:57+00:00 — device_connection (source: synthetic_activity)
- 2026-01-28T03:09:05+00:00 — transaction (source: synthetic_payments)
- 2026-01-31T09:38:15+00:00 — transaction (source: synthetic_payments)
- 2026-02-03T06:23:05+00:00 — transaction (source: synthetic_payments)
- 2026-02-05T02:48:23+00:00 — transaction (source: synthetic_payments)
- 2026-02-08T23:14:08+00:00 — transaction (source: synthetic_payments)
- 2026-02-11T05:50:39+00:00 — transaction (source: synthetic_payments)
- 2026-02-12T22:55:07+00:00 — transaction (source: synthetic_payments)
- 2026-02-14T12:02:55+00:00 — communication (source: synthetic_activity)
- 2026-02-18T10:05:32+00:00 — transaction (source: synthetic_payments)
- 2026-02-18T16:20:39+00:00 — login (source: synthetic_activity)
- 2026-02-19T03:37:13+00:00 — transaction (source: synthetic_payments)
- 2026-02-22T12:00:38+00:00 — device_connection (source: synthetic_activity)
- 2026-02-22T18:46:54+00:00 — transaction (source: synthetic_payments)
- 2026-02-26T13:42:45+00:00 — transaction (source: synthetic_payments)
- 2026-02-28T18:21:22+00:00 — transaction (source: synthetic_payments)
- 2026-02-28T23:12:08+00:00 — transaction (source: synthetic_payments)
- 2026-02-28T23:22:34+00:00 — transaction (source: synthetic_payments)
- 2026-03-01T01:18:00+00:00 — auth_failure (source: synthetic_activity)
- 2026-03-01T01:30:00+00:00 — login (source: synthetic_activity)
- 2026-03-01T01:42:00+00:00 — device_connection (source: synthetic_activity)
- 2026-03-01T01:44:00+00:00 — dns_query (source: synthetic_activity)
- 2026-03-01T02:00:00+00:00 — transaction (source: synthetic_payments)
- 2026-03-01T02:10:00+00:00 — location_change (source: synthetic_activity)
- 2026-03-02T02:00:00+00:00 — transaction (source: synthetic_payments)
- 2026-03-02T20:32:28+00:00 — transaction (source: synthetic_payments)
- 2026-03-03T02:00:00+00:00 — transaction (source: synthetic_payments)

## Geographic Findings

- points: 151
- bbox: [-87.687776, 1.224032, 139.75541, 53.588217]
- most_frequent_locations: [{'location_id': 'loca_5675d648038e54a18cf6', 'events': 49}, {'location_id': 'loca_22a8bfc43e2d79f6d063', 'events': 7}, {'location_id': 'loca_9adbe7c6eed2a8608e85', 'events': 2}, {'location_id': 'loca_2cedbf4427ee87d361aa', 'events': 2}, {'location_id': 'loca_318c41afac5d72054c7c', 'events': 2}]

## Analytical Signals

> Signals are not conclusions. Review evidence and alternative explanations.

### ANALYTICAL SIGNAL — suspicious_domain_dns (v1, score 1.0)

Event 'dns_query' at 2026-03-19T01:44:00+00:00 involves watch-listed entity(ies).

Alternative explanations:
- Security scanner or sandbox detonation
- Link preview fetched by a messaging app
- Watch-list entry is stale

### ANALYTICAL SIGNAL — suspicious_domain_dns (v1, score 1.0)

Event 'dns_query' at 2026-03-16T01:44:00+00:00 involves watch-listed entity(ies).

Alternative explanations:
- Security scanner or sandbox detonation
- Link preview fetched by a messaging app
- Watch-list entry is stale

### ANALYTICAL SIGNAL — suspicious_domain_dns (v1, score 1.0)

Event 'dns_query' at 2026-03-13T01:44:00+00:00 involves watch-listed entity(ies).

Alternative explanations:
- Security scanner or sandbox detonation
- Link preview fetched by a messaging app
- Watch-list entry is stale

### ANALYTICAL SIGNAL — suspicious_domain_dns (v1, score 1.0)

Event 'dns_query' at 2026-03-10T01:44:00+00:00 involves watch-listed entity(ies).

Alternative explanations:
- Security scanner or sandbox detonation
- Link preview fetched by a messaging app
- Watch-list entry is stale

### ANALYTICAL SIGNAL — suspicious_domain_dns (v1, score 1.0)

Event 'dns_query' at 2026-03-07T01:44:00+00:00 involves watch-listed entity(ies).

Alternative explanations:
- Security scanner or sandbox detonation
- Link preview fetched by a messaging app
- Watch-list entry is stale

### ANALYTICAL SIGNAL — suspicious_domain_dns (v1, score 1.0)

Event 'dns_query' at 2026-03-04T01:44:00+00:00 involves watch-listed entity(ies).

Alternative explanations:
- Security scanner or sandbox detonation
- Link preview fetched by a messaging app
- Watch-list entry is stale

### ANALYTICAL SIGNAL — suspicious_domain_dns (v1, score 1.0)

Event 'dns_query' at 2026-03-01T01:44:00+00:00 involves watch-listed entity(ies).

Alternative explanations:
- Security scanner or sandbox detonation
- Link preview fetched by a messaging app
- Watch-list entry is stale

### ANALYTICAL SIGNAL — shared_ip (v1, score 1.75)

IPAddress ipad_b18172c56cc969123014 has CONNECTED_TO relationships with 7 distinct Account entities within 30 days (threshold > 4).

Alternative explanations:
- Carrier-grade NAT or corporate proxy
- Public Wi-Fi
- VPN exit node

### ANALYTICAL SIGNAL — shared_device (v1, score 1.4)

Device devi_c54142cba994ccc51e36 has USED relationships with 7 distinct Account entities within 30 days (threshold > 5).

Alternative explanations:
- Shared family or household device
- Shop / kiosk / library terminal
- Customer-support staff device
- Device-ID collision or telemetry defect
- Emulator farm used for QA testing

### ANALYTICAL SIGNAL — inbound_burst (v1, score 2.5)

Account acco_84e3919c2440205c183f has 20 TRANSFERRED_TO relationships in a 7-day window; population p99 is 3 (mean 1.6, n=1981 Accounts).

Alternative explanations:
- Payroll or merchant settlement account
- Seasonal business activity
- Batch migration of legacy records

### ANALYTICAL SIGNAL — harbor_geofence (v1, score 14.0)

Device devi_c54142cba994ccc51e36 recorded 14 event(s) inside geofence 'Harbor Plaza perimeter' between 2026-03-01T01:30:00+00:00 and 2026-03-19T01:42:00+00:00.

Alternative explanations:
- Busy public location; presence is expected for many people

### ANALYTICAL SIGNAL — auth_failure_then_login (v1, score 1.0)

'auth_failure' followed by 'login' after 12 min from the same IP.

Alternative explanations:
- User mistyped the password
- Password manager sync delay

### ANALYTICAL SIGNAL — auth_failure_then_login (v1, score 1.0)

'auth_failure' followed by 'login' after 12 min from the same IP.

Alternative explanations:
- User mistyped the password
- Password manager sync delay

### ANALYTICAL SIGNAL — auth_failure_then_login (v1, score 1.0)

'auth_failure' followed by 'login' after 12 min from the same IP.

Alternative explanations:
- User mistyped the password
- Password manager sync delay

### ANALYTICAL SIGNAL — auth_failure_then_login (v1, score 1.0)

'auth_failure' followed by 'login' after 12 min from the same IP.

Alternative explanations:
- User mistyped the password
- Password manager sync delay

### ANALYTICAL SIGNAL — auth_failure_then_login (v1, score 1.0)

'auth_failure' followed by 'login' after 12 min from the same IP.

Alternative explanations:
- User mistyped the password
- Password manager sync delay

### ANALYTICAL SIGNAL — auth_failure_then_login (v1, score 1.0)

'auth_failure' followed by 'login' after 12 min from the same IP.

Alternative explanations:
- User mistyped the password
- Password manager sync delay

### ANALYTICAL SIGNAL — auth_failure_then_login (v1, score 1.0)

'auth_failure' followed by 'login' after 12 min from the same IP.

Alternative explanations:
- User mistyped the password
- Password manager sync delay

## Evidence

- [signal] Shared device signal (SYSTEM_INFERENCE)
- [citation] Source record row-1985-68bda6098096 (ANALYST_ASSERTION)
- [note] Alternative explanations to check (ANALYST_ASSERTION)

## Analyst Assertions

> Hypotheses recorded by analysts — not source-derived facts.

- **ANALYST ASSERTION — HYPOTHESIS**: The seven accounts that used DV-7F3A-SHARED may be operated by a common party. — by usr_6f141f39bfcd4cfe

## Data Sources

- Authentication & activity log (synthetic) (synthetic_activity, SYNTHETIC / DEMONSTRATION DATA): 50 records, transformations map-1.0+05ca4403
- Core banking accounts (synthetic) (synthetic_core_banking, SYNTHETIC / DEMONSTRATION DATA): 8 records, transformations map-1.0+ca228620
- Device inventory (synthetic) (synthetic_device_intel, SYNTHETIC / DEMONSTRATION DATA): 1 records, transformations map-1.0+ad29d28d
- Device-session telemetry (synthetic) (synthetic_device_usage, SYNTHETIC / DEMONSTRATION DATA): 14 records, transformations map-1.0+9eaa9e32
- Passive DNS (synthetic) (synthetic_dns, SYNTHETIC / DEMONSTRATION DATA): 1 records, transformations map-1.0+b8b4659f
- Payments ledger (synthetic) (synthetic_payments, SYNTHETIC / DEMONSTRATION DATA): 108 records, transformations map-1.0+4a2dcbb6

## Limitations

- All results depend on the completeness and accuracy of ingested sources; absence of data is not evidence of absence.
- Relationships reflect recorded associations. They do not by themselves establish intent, causation, control or wrongdoing.
- Analytical signals are outputs of deterministic rules and graph mathematics. They are prompts for review, not findings.
- Entity resolution is deterministic but imperfect: unmerged duplicates and incorrect merges are both possible.
- Graph views and path searches are windowed and fan-out limited; truncated searches may omit connections.
- Analyst assertions are hypotheses recorded by people and have not been independently verified unless stated.
