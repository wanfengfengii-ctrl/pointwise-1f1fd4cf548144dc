# 接线复测交班台账

精密装配试验线用工单统一两站的公共端子编号。白班站员登记证据和误录更正，夜班在站源关闭后按指定站件核账，质控员凭正式班报安排复测。更正可以产生新站件和新班报，原正式号随时可重印。

## 运行

使用 Python 3.11 和标准库。在项目根目录运行 `python3 -B check_project.py` 执行平台标准全量回归，或运行 `python3 -B demo.py` 演示。标准回归入口由平台提供，发现 `tests` 下的全部 `test_*.py`。演示只读 `examples/shift.json`，在临时目录建立甲站、乙站和中心的三个 SQLite 文件。

## 一班交接

1. 试验员用工单试验号、两个站号和端子目录登记试验。每个独立站库使用同一份工单，登记同时生成两站的空修订 0。重复初始化和同参登记保有已提交的数据。
2. 站员以明确基修订提交观察批次。更正通过记录号指认旧记录，整批有效才生成新快照。旧修订仍可按号查阅和签发。
3. 站员核对指定修订的公共状态条件代价。状态取整数 0 或 1，同态要求相等，异态要求不等。硬证据是可行条件。每条被违反的软证据逐条增加其权重。
4. 站端将每组完整公共状态的可行性及最低站内代价冻结成 V1 站件，同时写入签发回执。原观察及本站接点身份留站。
5. 夜班接纳两个固定件。首次接纳封存完整业务内容和接纳号。纯 JSON 空白和对象键顺序差异视为重送。相同件号的异内容拒收。
6. 关源后，夜班用两个件号和一个有序端子对签报。中心按公共端子身份对齐，对共同可行的同一完整状态累计两站代价。所有最低代价状态都参与端子对投影，结果字典序去重。重复端子合法。
7. 班报和成功回执一次提交。无共同硬解释、输入错误或提交失败均无新报告和成功回执，已接纳件继续可用。
8. 质控员按原号读取或导出封存值。更正后的新件可用于另一次复核。原报告仍引用原件和原修订。

每个试验支持 1–6 个公共端子，每站每修订支持至多 6 个本地接点、24 条观察。空修订在每个公共状态下成本为 0。条件成本和总代价使用精确整数。硬不可行与代价 0 分别表示。样例中甲站的 `X=u` 和 `u=Y` 为硬证据，乙站的 `X≠Y` 为权重 1 的软证据。夜班签出代价 1 和 `((0, 0), (1, 1))`。把甲站第二条改成异态后，新报代价为 0，支持 `((0, 1), (1, 0))`。

## Python 接口

连接使用 `sqlite3.Connection`。站库先调用 `evidence.revision_store.initialize_evidence_store(db)`，然后调用 `station.issue.initialize_issue_store(db)`。中心库调用 `intake.store.initialize_intake_store(db)` 和 `reports.register.initialize_report_store(db)`。重新打开的连接使用相同初始化入口。持久写入由调用的业务入口负责提交，传入的连接须处于无活动事务状态。

| 调用 | 返回 |
| --- | --- |
| `evidence.trials.open_trial(db, trial_id, stations, terminals)` | `PublicCatalog`，工单、两个站号及有序公共目录。 |
| `evidence.revisions.revise_evidence(db, trial_id, station_id, base_revision, changes)` | `RevisionSnapshot`，含新修订号、父修订及证据快照。 |
| `evidence.revisions.read_revision(db, trial_id, station_id, revision)` | 指定站修订的快照。 |
| `station.audit.audit_revision(db, trial_id, station_id, revision)` | `AuditedRevision`，`analysis.cost_for(bits)` 按目录顺序返回整数或 `None`。 |
| `station.issue.issue_package(db, trial_id, station_id, revision)` | `(wire, IssueReceipt)`，可接纳的 JSON 文本及签发回执。 |
| `station.issue.read_issued_package(db, package_id)` | 原 `(wire, IssueReceipt)`，缺失返回 `None`。 |
| `intake.registry.accept_package(db, wire)` | `AcceptedPackage`，含首次接纳号、件号、内容摘要及规范文本。 |
| `intake.registry.get_accepted_package(db, package_id)` | 可独立使用的 `ValidatedPackage`，缺失返回 `None`。 |
| `review.request.sign_report(db, left_id, right_id, terminals)` | `(ReportSnapshot, PublishReceipt)`。由回执取得正式号。 |
| `reports.read.read_report(db, report_id, mode='read')` | 封存快照；`mode='export'` 返回可重印的 JSON 文本。未知号在两种模式下均返回 `None`。 |
| `reports.register.load_publish_receipt(db, report_id)` | 正式发布回执，缺失返回 `None`。 |

试验、站、端子、观察和站件的标识以 ASCII 字母或数字开头，后续可使用 ASCII 字母、数字、点、连字符和下划线，总长 1–96。目录、批次和请求对使用列表或元组。用 `EndpointRef('public', 'X')` 表示公共接点，`EndpointRef('local', 'u', 'A')` 表示 A 站本地接点。`Observation(record_id, left, right, relation, kind, weight)` 使用 `same` 或 `different` 作为关系，`hard` 观察的权重为 `None`，`soft` 观察的权重为正整数。`EvidenceChange(operation, record_id, observation)` 支持 `add`、`replace` 和 `remove`，删除时省略 observation。每批每个记录号至多出现一次，修订可以从任意已有基修订建立。

非法参数、异内容冲突或跨试验请求抛出 `ValueError`，硬证据无共同解释抛出 `review.request.NoCommonExplanation`（`ValueError` 子类）。需存在的试验、修订或已接纳件缺失时抛出 `KeyError`。SQLite 持久化失败保留 `sqlite3.Error`。

## 便携件和重印

V1 站件外层字段为 `version`、`package_id`、`source`、`catalog` 和 `conditions`。`source` 含 `trial_id`、`station_id`、`revision`；`catalog` 含 `trial_id`、`stations`、`terminals`。两处试验号须相同，来源站须属于目录。中心按完整内容判断固定件是否相同，以件内身份及目录校验归属。

当前编码的 `conditions.encoding` 是 `lex-costs`。`conditions.costs` 的长度为 `2**len(terminals)`，按目录顺序上的二值全状态字典序填写。例如目录 `["X", "Y"]` 的同态硬证据条件表是 `["0", null, null, "0"]`。代价用无前导零的十进制整数文本，`null` 表示硬不可行。重印 JSON 的 `minimum_cost` 同样是十进制整数文本，Python 班报字段仍为整数。导出固定正式号、试验、请求端子、代价、组合及两件原出处，并记录本次导出。

## V2 批准费用豁免班报

`WAIVERS.md` 定义夜班复核能力，规则摘要如下。所有 V1 接口、编码和回归保持可用；V2 与 V1 件、报告可在同一中心库共存。

| 调用 | 返回 |
| --- | --- |
| `evidence.trials.register_waiver_policy(db, trial_id, groups, approved_combinations)` | 字典 `{"groups": (...), "approved_combinations": ((...), ...)}`，全部按字典序排列，空组合自动包含。政策首登后内容固定，同工单同内容重投返回同值，改内容报 `ValueError`，缺工单报 `KeyError`。 |
| `Observation(..., fee_group=None)` | 仅软证据可指定已登记组名；硬证据或未登记组名报 `ValueError`，整批不写入。替换时省略 `fee_group` 恢复普通计费。 |
| `station.issue.issue_waiver_package(db, trial_id, station_id, revision)` | `(wire, IssueReceipt)`，V2 件绑定确切修订与完整政策。未知修订或未登记政策报 `KeyError`。`read_issued_package` 同时领取 V1/V2 原件。 |
| `intake.registry.accept_package(db, wire)` | 同时接纳 V1/V2。V2 校验来源、完整政策、条件载荷格式、覆盖、金额单调性与硬可行性一致性。 |
| `review.request.sign_waiver_report(db, left_id, right_id, terminals, waived_groups)` | `(ReportSnapshot, PublishReceipt)`。两件须为同工单异站 V2 件且政策一致；混版、政策不符或未批准组合报 `ValueError`，无共同硬解释报 `NoCommonExplanation`。 |

V2 件外层为 `version`（整数 `2`）、`package_id`、`source`、`catalog`、`policy`、`conditions`。`policy` 含 JSON 数组形式的 `groups` 与 `approved_combinations`（含空组合）。`conditions.encoding` 为 `waiver-lex-costs`，`conditions.tables` 对每个批准组合给出一张完整公共状态代价表，每张表带 `combination`（组名数组）与 `costs`（字典序全状态，十进制整数文本或 `null`）。豁免只免除所选组合内归组软证据的违例费，硬约束不变；同一公共状态的硬可行性在所有组合下相同。中心接纳时按规范化内容比较：JSON 空白、对象键序、政策集合排列及表序差异视为等价，同号异内容拒收，同号等价重投沿用原接纳号。

V2 班报在 V1 五字段（`trial_id`、`terminals`、`minimum_cost`、`pairs`、`sources`）之外另存 `policy`（与登记返回值同形的 Python 快照，实际使用组为字典序元组）和 `waived_groups`。`read_report(..., mode='export')` 的重印 JSON 对 V2 追加这两个业务字段，V1 报告仍只有原六字段（含 `report_id`）。旧件旧报告的接口与编码不变。

运行 `python3 -B waiver_examples.py` 可对三组样例同时核对 V1 手算表与 V2 两种口径；`python3 -B demo.py` 在原班报演示之后追加断源签发、费用口径更正与原号重印的豁免演示。
