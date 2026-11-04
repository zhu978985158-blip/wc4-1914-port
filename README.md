# 世界征服者4：1914 地图移植研究工具

**对应游戏：《世界征服者4 / World Conqueror 4》，研究对象是 Android 版的地图与征服场景数据。** 这不是独立游戏，也不是下载后即可安装试玩的完整 Mod。

This repository contains research tools from a **World Conqueror 4** scene-31 / 1914 map-porting project: BTL conversion, general-ID conflict auditing, a version-specific ARM64 map-transition patch, and APK comparison. No game, APK, map assets, signing keys or complete playable mod are included.

目标曾是把来源“帝国”修改包的 1914 场景迁移到另一份特定的 `1.28` 底包，尽量保护既有场景及加速功能。**工程部分完成，未达到完整稳定版标准。** 本仓库只公开其中可独立解释与测试的自写工具，不提供复现最新内部测试 APK 的完整组装链。

详细进度、历史判断更正和未完成项见 [项目状态](docs/STATUS.md)。

## 工具能做什么

| 工具 | 输入 | 输出与用途 | 主要限制 |
| --- | --- | --- | --- |
| `tools/audit_scene31.py` | 匹配版本的底包 APK、来源 APK | 分析 `conquest31.btl` 的将领 ID 冲突，生成隔离的重映射 BTL、追加将领记录和 JSON 审计 | 只覆盖已知 v1 布局与将领字段，不能验证技能、事件和兵种运行语义 |
| `tools/convert_scene31_v3.py` | 含 `assets/stage/conquest31.btl` 的来源 APK | 把特定 v1 的 48 字节军队记录扩展为 v3 的 64 字节记录，输出新 BTL 与审计 | 拒绝不支持的布局或增援；结构保真不等于目标引擎完整兼容 |
| `tools/patch_map2_transition.py` | 匹配研究版本的 ARM64 ELF 原生库 | 生成单独的新库及分支/改动范围审计，处理涉及地图 2 的切换初始化 | 使用固定地址与二进制前置条件，不是通用补丁，不会构建或安装 APK |
| `tools/audit_base_diff.py` | 底包 APK、候选 APK | 列出变更/新增/移除文件，检查历史研究中指定的程序和原征服保护范围 | 静态保护检查不覆盖完整资源语义，也不是运行验收 |

这些工具只读取你明确提供的输入，生成新输出或打印报告。源码不查找已安装游戏、不读取正式存档，也不负责签名、安装或模拟器操作。

## 需要自己准备什么

- Python 3。BTL 转换、场景审计和 APK 比较使用标准库。
- 原生 ELF 补丁需要 `capstone` 与 `pyelftools`；本次合成测试使用的版本已记录在 `requirements.txt`。
- 若运行真实数据研究，须自行准备与原研究匹配的底包和来源 APK。任意官方版本或其他修改包不能视为可互换输入。
- 原生补丁的 `.so` 必须从匹配底包中自行取得。本仓库不附带游戏程序、原地图、人物、贴图、图集、签名密钥或第三方反编译代码。

建议使用独立 Python 环境：

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

所有命令在仓库根目录运行。`inputs/`、`outputs/`、常见游戏二进制及签名密钥后缀已列入忽略规则。**不要使用 `python -O`**：格式与原生补丁工具会拒绝优化模式，避免跳过保真断言。

## 1. 分析来源场景及将领 ID 冲突

```sh
python3 tools/audit_scene31.py \
  --base inputs/base.apk \
  --source inputs/source.apk \
  --output outputs/scene31
```

默认底包与来源位置也是 `inputs/base.apk`、`inputs/source.apk`。工具读取两包的 `assets/json/GeneralSettings.json` 以及来源的 `assets/stage/conquest31.btl`，输出：

- `conquest31.general-remap.btl`：只重映射已确认冲突的将领 ID 字段。
- `GeneralSettings.append.json`：候选追加记录，将导入将领的 `InShop` 设为 `0`。
- `scene31.audit.json`：场景分区、冲突映射、缺失来源将领与边界检查信息。

工具从未占用的 `40000` 起分配候选 ID，并检查只有声明的将领字段发生变化。缺失来源记录不会被臆造；报告中的问题需要人工继续调查。输出目录用于生成研究文件，重复运行会更新其中同名派生结果。

此解析器只处理原研究使用的受限 v1 布局。增援、空袭、陷阱等扩展段或长度不匹配会被拒绝；不能用它来证明任意 BTL 都被完整解析。

## 2. 做受限的 BTL v1 → v3 结构转换

```sh
python3 tools/convert_scene31_v3.py \
  inputs/source.apk outputs/conquest31.v3.btl
```

转换保留原军队记录的 48 字节，在每条后面补 16 个零字节，并更新头部版本。源码会逆向重建输入，验证原始字节可完全还原；不推断新字段语义，也不重写兵种数值。

同时生成 `outputs/conquest31.v3.btl.audit.json`，记录输入/输出哈希、长度、分区与结构转换状态。输出和报告必须是新路径；已经存在或与输入相同会停止，而不会覆盖原包。

## 3. 检查并生成地图 2 原生切换补丁

```sh
python3 tools/patch_map2_transition.py \
  inputs/libworld-conqueror-4.so outputs/libworld-conqueror-4.map2.so
```

这一步是**针对特定引擎布局的实验补丁**：检查 ARM64、小端 ELF、既定入口指令、可用的零填充间隙及段属性，然后在研究地址 `0x231fec` 修改跳转、增加 36 字节逻辑并调整 ELF 段长度。输入不满足任一前置条件时应停止，不能通过删除断言强行应用到别的版本。

审计报告为输出路径后附 `.audit.json`，含完整允许修改范围、反汇编和已定位加速区域的字节不变性检查。原输入库保持不动。

**加速区域字节不变不等于加速功能已通过运行回归。** 本工具不补全地图数据，不处理其余资源/技能依赖，也不签名或安装生成文件。

## 4. 比较候选 APK 与底包

```sh
python3 tools/audit_base_diff.py inputs/base.apk inputs/candidate.apk \
  > outputs/apk-diff.json
```

重定向前先创建 `outputs/`。工具不改 APK；输出包含变化分类、意外变化列表、非签名文件移除列表与候选哈希。返回 `0` 表示历史保护规则未发现阻断；发现阻断时仍打印报告并返回 `1`。

保护规则重点检查 `classes.dex`、`classes2.dex`、`lib/arm64-v8a/libworld-conqueror-4.so` 和原有征服场景（专门导入的 `conquest31.btl` 除外），以及非签名文件移除。`unexpected_changed_existing_entries` 仍需人工审阅；`BASE_PROTECTION_PASS` 不是对任意 APK、所有新增代码或全部资源的全面安全保证。

如果候选已经应用地图 2 原生补丁，这个严格保留原生库的历史规则会报告程序变化。不能为了得到 PASS 而扩大白名单；应分别检查原生补丁的改动范围、整包差异及真实运行回归。

## 测试与本次验证

```sh
python3 -m unittest discover -s tests -v
```

测试只在临时目录或内存中生成完全合成的 BTL、ARM64 ELF 与 ZIP 数据；不需要真实 APK、地图、签名密钥、模拟器或存档。覆盖：

- 军队记录转换的字节保真、零扩展与结构长度；
- 截断或不支持的格式拒绝；
- 场景将领冲突的隔离 ID 重映射，以及输入 APK 不变；
- 转换命令的独立输出和审计报告；
- 二进制输出命令拒绝覆盖输入或已有结果；
- 原生程序变化识别与分类；
- ARM64 补丁的允许修改范围、受保护加速区域及错误架构拒绝；
- 优化模式不能关闭格式检查。

**本次未生成或运行真实游戏包。** 历史记录曾在 Android 模拟器中进入 1914 第一回合并进行部分操作，但完整长回合、存读档、多个国家、加速对照和实体设备验收未完成，详见 [项目状态](docs/STATUS.md)。

## 为什么没有完整一键移植命令

原项目有多轮内部候选和人工核对的数据。早期组装还出现过导入兵种继承不相关目标模板字段的问题；部分旧门槛脚本的环境结论也已过时。本次没有把这些旧脚本简单串成一个“完成版”入口。

当前工具集能够维护和验证上述独立研究步骤，但**不能从这份仓库单独复现最新内部 APK，也不能承诺来源玩法原样保留**。继续完成整张地图，需要重新闭合兵种、技能、事件、图集和生产选择的数据依赖，并建立完整构建及回归流程。

代码可见性不改变原游戏、来源修改包和第三方工具各自的权利范围。仓库未分发这些二进制或素材；对外分发任何真实候选包前，应另行确认适用授权。
