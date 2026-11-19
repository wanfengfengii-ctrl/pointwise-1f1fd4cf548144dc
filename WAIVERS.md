# 批准费用豁免的接线复测班报

原班报按 README.md 的规则运行。新增班报用于工单已经批准费用豁免、两站已关库的夜班复核。夜班只提供两份已接纳站件、批准组合和端子对。白班的原记录号及私有接点留在源库。

## 白班登记与签发

- 使用 README.md 的初始化入口打开或重开库。先以原 `open_trial` 登记工单，再调用 `evidence.trials.register_waiver_policy(db, trial_id, groups, approved_combinations)`。`groups` 是组名列表或元组，组名沿用原标识规则且唯一。`approved_combinations` 是组合列表或元组，每个组合是互异已声明组名的列表或元组。组合按组名集合比较，批准清单中重复的组合无效。空组合可显式列出，省略时自动包含。返回 `{"groups": (...), "approved_combinations": ((...), ...)}`，组名、组合内的组名以及组合清单均按字典序排列。
- 工单的政策内容首次登记后固定。同工单以相同内容重投返回相同值，改变内容报 `ValueError`。不同站库可分别登记，中心在选件时核对两件的完整政策内容。缺少工单报 `KeyError`。
- `evidence.observations.Observation` 新增可选参数 `fee_group=None`。原 `revise_evidence` 将归组随记录写入新修订。仅软证据可指定已登记组名，硬证据或政策未登记时指定组名报 `ValueError`，整批不写入。未修改的记录保留基修订归组，替换记录用替换值的归组，替换时省略归组表示恢复普通计费。V1 库中原有记录视为未归组。工单中已声明而本站未使用的组仍有效。
- `station.issue.issue_waiver_package(db, trial_id, station_id, revision)` 返回 `(wire, IssueReceipt)`，绑定确切修订与该工单完整政策。未知修订或未登记政策报 `KeyError`。V2 件与回执同时保存，沿 `read_issued_package` 领取原件。原 `issue_package` 仍发行普通计费的 V1 件。

## 便携件与中心复核

V2 JSON 外层为 `version`、`package_id`、`source`、`catalog`、`policy`、`conditions`，其中 `version` 为整数 `2`。来源、目录、标识及来源和目录的一致性沿用 V1。`policy` 含 `groups` 和 `approved_combinations`，使用 JSON 数组表达登记的完整内容，含空组合。`conditions` 为带 `encoding` 字段的对象，内部表示由交付方选择并注明。它须针对每个批准组合和每个完整公共状态兑现硬可行性与精确的最低站内代价。货币值沿用 V1 的无前导零十进制整数文本。硬不可行与零须可区分，同一公共状态的硬可行性在所有组合下相同。

计费仍逐条计算。违反硬证据的解释不可用。被选组合中归组软证据的违例费用为零，其余违反的软证据按原权重计费。在本次组合下确定本站每个公共状态的最低值。允许对全部状态和批准组合重算。件中只交付公共目录、来源、政策及核账所需条件证据。原观察记录号和本站接点标识留站。

中心仍用 `intake.registry.accept_package(db, wire)` 接纳，支持 V1 和 V2。中心校验收到内容的来源、完整政策、条件载荷的格式、覆盖、金额和硬可行性的一致性。非法件报 `ValueError`。同件号重投按完整内容判断。JSON 空白、对象键序和政策各集合的排列差异视为等价，其他数组位置按对应编码解释并参与内容比较。同号等价重投沿用原接纳号，同号异内容拒收。

`review.request.sign_waiver_report(db, left_id, right_id, terminals, waived_groups)` 返回 `(report, PublishReceipt)`。`waived_groups` 为互异已声明组名的列表或元组，须在批准清单中，可传空。两件须为同一工单的不同站 V2 件，目录的身份校验沿 V1，完整政策内容须一致，即便本次只请求空组合。选择同一个组合后，按公共端子身份在同一完整状态上合算，求精确整数最低代价，并按 V1 规则对全部最优状态投影、排序和去重。请求端子有序，允许重复。原 `sign_report` 接收 V1 件。未知件报 `KeyError`，非法、混版、政策不符及未批准组合报 `ValueError`，无共同硬解释报 `review.request.NoCommonExplanation`。

新班报保留 V1 报告的 `trial_id`、`terminals`、`minimum_cost`、`pairs`、`sources`，另有 `policy` 和 `waived_groups`。Python 快照中的政策值与登记返回值同形，实际使用的组为字典序元组。原 `read_report(db, report_id, mode='read')` 读取固定值，`mode='export'` 返回重印 JSON，保留同样的业务字段及原 `report_id`，元组转为数组，金额沿用 V1 的十进制整数文本。旧件与旧报告保留原接口和编码。回执沿 `load_publish_receipt` 领取，未知报告号沿用 V1 缺失语义。新班报、政策、采用组合、两件出处及成功回执同次提交。SQLite 提交错误保留原异常，签发、接纳或发布失败无半笔成果，原请求可重试。后续更正及中心重开后，从已封存的报告读值并重印。

## 交班样例与核验

`waiver_examples.py` 提供三组可直接构造的 V1 证据、拟登记的归组和手算预期。可先运行 `python3 -B waiver_examples.py` 检查现有两件和原报告。脚本中的 `expected_v2` 是手算预期。

接入新能力后，在甲、乙两份源库各调用 `register_waiver_policy(source, 'bench-waiver', ['G'], [[], ['G']])`。使用样例的 `grouped` 记录建修订，仅在甲站 `fee-A` 上指定 `fee_group='G'`。由 `issue_waiver_package` 取出两份文本，在中心调用 `accept_package` 并保存其 `package_id`。关闭两站后调用 `sign_waiver_report(center, a_id, b_id, ['X', 'Y'], [])` 得到 `2` 和 `((0, 1), (1, 0))`。将组合换成 `['G']` 得到 `1` 和 `((0, 0), (1, 1))`。甲站把 `fee-A` 改为未归组再签新件后，选新件免 G 应得 `2` 和异态对。重开中心，用旧正式号重印仍得到原 G 口径、代价 `1` 和原双件出处。

`private-choice` 中，甲站同一私有接点的两个解释各自只支付普通费 2 或 G 费 3，乙站无记录。两种口径都允许四种端子对，普通最低值为 2，免 G 为 0。若给甲站加 X、Y 同态硬条件并给乙站加异态硬条件，则任何批准组合都无法签报。若一个合法件批准空组合与免 G，另一个只批准空组合，则请求空组合也拒签。

原 `tests/fixtures.py` 的 `install_commit_block(db, 'issue_receipts')` 与 `install_commit_block(db, 'publish_receipts')` 可为原签发、发布事务注入真实提交失败。用同等提交失败场景核对新路径回滚和重试。沿 `.pointwise-runtime.json` 的 `verify` 入口接通原回归和新增业务核验，核对失败时返回非零。沿 `demo` 入口展示断源签发、费用口径更正及原号重印的真实结果。简述交付的条件载荷及收件方使用它时依赖的正确性条件。
