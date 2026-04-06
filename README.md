# **115\_Helper 容器化网页软件产品需求与底层技术架构深度解析报告：基于 115 网盘原生 API 的重构与实现**

## **核心架构范式的演进与重构逻辑**

在开发一款面向复杂媒体库管理的容器化网页软件时，底层架构的选型直接决定了系统的性能上限、网络 I/O 消耗以及长任务的稳定性。115\_Helper 的初始概念设计依托于 CloudDrive2（简称 CD2）的 gRPC API 指南进行构建。CD2 作为一款优秀的云盘挂载与聚合工具，其 gRPC API 提供了传输任务管理、远程上传、挂载管理以及 WebDAV 协议集成的标准框架 1。该指南还为 C\#、Java、Go 和 Python 提供了详尽的配置说明与身份验证机制 1。然而，针对海量影视文件的深度元数据解析、跨目录重组以及高频的文件移动与复制请求，将 CD2 作为中间代理层会引入不可忽视的架构瓶颈。

基于 WebDAV 或虚拟文件系统挂载的传统操作逻辑，往往会将云端的抽象文件映射为本地系统的物理字节流。当用户或后台程序试图通过虚拟路径执行一个体积高达数十 GB 的 ISO 镜像文件复制或移动指令时，极易触发底层文件系统的数据全量拉取与重传。这种“伪本地”操作不仅会瞬间榨干容器所在宿主机的网络带宽，还可能触发云盘服务商严格的 API 速率限制（Rate Limiting），导致任务大面积失败。

为了彻底解决这一性能瓶颈，本需求报告提出了一次根本性的技术路线转移：舍弃通过 CD2 的 gRPC 接口层进行间接操作，转而直接集成 115 网盘的原生 API（Native API）。通过直接调用 115 网盘的 Web 端、App 端或开放平台接口，软件可以下发纯粹的服务器端指令，将复杂的文件操作降维为云端数据库节点指针的修改。这一技术演进的灵感来源于 GitHub 上的开源项目 AW115MST 2。该项目展示了如何通过智能检测 115 网盘的“秒传”状态，以极低的系统开销实现文件的自动分类与管理 2。通过引入 Python 生态中成熟的 115 SDK 组件，例如 py115 框架 3、115wangpan 离线扩展库 4，以及高度封装的 p115client 模块 6，115\_Helper 能够原生地贯彻“秒传转移优先，常规移动/复制兜底”的核心执行逻辑。这种逻辑确保了所有的文件梳理动作都能以 O(1) 的时间复杂度在云端瞬间完成，从而为用户提供一种无缝、极速的资产重组体验。

## **基于原生 API 的“秒传优先”传输引擎设计**

“秒传优先”机制是 115\_Helper 能够处理 PB 级多媒体数据的基石。在直接对接 115 原生 API 时，文件操作不再依赖物理层面的字节转移。Python 生态下的 p115client 客户端模块为这种高级文件系统操作提供了稳健的支持 6。该模块允许开发者通过直接封装 HTTP 请求的方式，调用 115 的各类核心功能，并原生支持同步与异步双轨操作模式 6。

在处理复杂任务时，115\_Helper 必须强制使用异步请求机制（即在调用时传入 async\_=True 参数），并结合高并发的 HTTP 异步请求库（例如 aiohttp 或 httpx），以防止在扫描包含数万个文件的庞大剧集目录时发生主线程阻塞 6。所有通过 API 下发的指令，其响应都必须经过严格的校验机制。系统需利用类似于 p115client.check\_response 的工具函数解析返回的 JSON 字典数据，并专门探测其中的 state 键值 6。只有当状态值返回 True 或 1 时，系统才推进后续的流转；一旦返回 False 或 0，系统必须立刻抛出定制化的操作系统级异常（如 P115OSError），并触发后备的重试或兜底逻辑 6。

当需要复制一个 ISO 文件时，常规系统会拉取文件流。但在“秒传优先”引擎中，系统首先会通过 API 获取目标 ISO 文件的唯一识别码（Pickcode）、SHA1 校验值以及文件精确字节大小。随后，系统将这些特征参数封装成一个伪造的“上传”或“秒传”请求，向 115 服务器的目标父目录发起握手。如果服务器端比对 SHA1 成功，文件将被瞬间克隆到新目录下，不仅不消耗任何上传带宽，更能够实现 100% 的元数据无损复制。

考虑到云盘接口的波动性以及秒传接口可能面临的权限收紧，借鉴 AW115MST 项目的理念，必须部署一套严密的“兜底方案” 2。如果秒传请求因状态异常或接口废弃而失败（即 state 不为 True），系统引擎应立刻降级到次优方案：利用 115 原生的“移动”（Move）接口。移动操作在云端仅表现为文件所属目录 ID 的变更，成功率极高且同样瞬时生效。若业务逻辑强制要求“复制”而非“移动”，且秒传不可用，系统最后才会调用云端的低速复制接口，甚至作为绝对的最后手段，启动内存缓冲区的分块流式传输。这种多级优雅降级的策略，确保了无论是面对孤立的文件还是庞大的目录树，软件都能保证文件整理任务的最终一致性。

## **功能集一：智能影视文件探测与高级拓扑穿透**

现代移动端播放应用虽然已经能够非常完善地硬解码包括 .mkv、.mp4、.ts、.rmvb 等在内的主流视频封装格式，但在处理包含复杂交互式菜单、多条字幕轨和角度切换的 ISO 蓝光原盘镜像文件时，依然面临极大的技术瓶颈。因此，115\_Helper 的首要任务就是针对已经通过媒体刮削工具（如 TinyMediaManager）整理好的结构化影视文件夹，进行外科手术式地靶向剥离与整理。

### **媒体目录拓扑结构的数学建模与遍历算法**

为了实现精准的穿透，系统首先必须理解并内化标准的媒体库拓扑结构。在媒体服务器（如 Emby、Jellyfin）的规范中，电影与剧集呈现出截然不同的目录树形态。

1. **电影文件拓扑（扁平化结构）：** 标准的电影刮削通常将所有的视觉资产、元数据和视频流容纳在一个单一的父目录内。例如，目录 上级多层目录/霸王花 (1988) {tmdb-68868} 作为“电影根节点”，其下一级子节点直接包含着视频文件（如 .iso 或 .mkv）、全局海报（poster.jpg）、背景图（backdrop.jpg）以及针对具体视频文件的元数据信息（同名 .nfo 文件）。针对电影，ISO 探测算法的穿透深度只需向上溯源一层，即“视频文件的上一级父目录”。  
2. **剧集文件拓扑（深层嵌套结构）：** 剧集的结构具有严格的层级划分。在“剧集根节点”（如 101次抢婚 (2023) {tmdb-222531}）之下，首先存放的是剧集级别的共享资产，如 tv\_show.nfo 和全局封面。其下嵌套着分季目录（如 Season 1）。在 season\* 目录下，才存放着真正的单集视频文件（如 101次抢婚.2023.S01E01.第1集.iso）、与该视频同名的单集 nfo 文件，以及该季专属的 season.nfo。因此，对于剧集文件，算法必须动态识别当前所处的目录特征，如果视频位于带有 season 关键字的目录下，穿透算法必须向上跨越两层，定位到其所在的 season\* 目录的上一级父目录作为操作的“根节点”。

基于上述拓扑结构，软件的 ISO 探测功能需要通过 115 原生 API 递归获取目标目录的 JSON 树状图，并对包含目标扩展名（.iso）的节点进行标注，最终在前端界面以表格形式呈现每一个 ISO 文件的绝对路径、体积、所属的逻辑“根节点”名称，供用户进行后续的批量勾选操作。

### **ISO 抽取与同级文件冲突消除逻辑（核心碰撞算法）**

本功能域中最具技术挑战的部分在于：同一部影视作品下可能混杂着多个不同清晰度或格式的视频副本（例如同一目录下同时存在 1080p 的 MKV 版本和蓝光原盘的 ISO 版本）。在对 ISO 进行移动、复制或删除时，如果粗暴地操作整个父目录，将会导致同目录下剩余的其他格式视频（如移动端友好的 MKV）瞬间失去所属的共享刮削信息（如海报），从而在 Emby 等流媒体前端变成无法识别的“孤儿文件”。

因此，在接收到针对某 ISO 文件的处理请求时，115\_Helper 必须在内存中构建一个该父目录下的“文件资产依赖图（Dependency Graph）”。该图基于文件的基础名称（Basename，即去除了最终后缀名的部分）进行严格的字符匹配运算。

系统内置了一个预设的“兄弟视频扩展名”黑名单矩阵 ![][image1]。

设当前目录下的所有文件集合为 ![][image2]，目标处理文件为 ![][image3]（此处为特定的 ISO 文件）。

算法将遍历集合 ![][image2]，若发现任何文件 ![][image4] 的扩展名 ![][image5] 且 ![][image6]，则判定存在“其他格式的视频文件”，即触发了“多版本碰撞状态”。

**文件资产分类矩阵定义：**

| 资产大类 | 包含的特征规则 | 示例文件 |
| :---- | :---- | :---- |
| **共有共享资产 (Shared Assets)** | 文件名不在任何视频文件的 Basename 集合中，且属于通用刮削命名（如 poster.jpg, backdrop.jpg, tv\_show.nfo 等） | backdrop.jpg, poster.jpg |
| **专属衍生资产 (Specific Assets)** | 文件名去后缀后的 Basename 与目标视频完全相等，属于特定视频的附属品（如专属 NFO、专属 ASS 字幕） | 霸王花...BeiTai.nfo 属于 ...BeiTai.iso 的专属资产 |
| **冗余隔离资产 (Isolated Assets)** | 属于碰撞状态下的其他兄弟视频及其衍生资产 | 霸王花...mkv 及其附属的 .ass 和 .nfo |

**基于碰撞状态的场景化动作执行方案：**

系统必须严格根据上述分类，通过 115 API 精准调度具体的云端操作。以下逻辑以需求中给出的“霸王花”目录为例进行深度拆解：

*场景 A：触发多版本碰撞（如示例中同时存在 .mkv 与 .iso 及其各自的 .nfo）*

在此状态下，系统的最高原则是：**绝对保障冗余隔离资产（MKV 系列）的完整性，使其在移动端继续提供完美的刮削展示。**

1. **复制请求 (Copy):** 系统会在目标路径下利用云端 API 创建同名的父目录结构（如新建 霸王花 (1988) {tmdb-68868}）。随后，提取出“共有共享资产”（backdrop.jpg, poster.jpg）与目标 ISO 的“专属衍生资产”（.iso 和对应的 .nfo），调用“秒传”或云端复制接口，将这四个文件精确投放至新目录中。原始目录不做任何删改。  
2. **移动请求 (Move):** 系统在目标路径建立新目录结构。首先，依然使用云端复制接口，将“共有共享资产”克隆一份到新目录。**此时绝不能移动共享资产**，否则源目录的 MKV 将失去海报。接着，使用云端移动接口（瞬间变更父节点 ID），将目标 ISO 及其专属的 .nfo 抽离源目录，投放至新目录。  
3. **删除请求 (Delete):** 系统向 API 下发精准删除指令，仅删除目标 ISO 文件以及属于该 ISO 的专属衍生资产（同名 .nfo），共享的海报图片和整个父目录结构毫发无损。

*场景 B：未触发多版本碰撞（目录内仅存在唯一的 ISO 视频格式）*

当系统确认该目录下没有其他视频格式时，整个目录被视为 ISO 的单一连带实体。

1. **复制请求 (Copy):** 直接针对包含该 ISO 文件的父目录触发云端目录级复制，包含目录内的所有视频、NFO、海报图，连同目录壳一起全量克隆至目标节点。  
2. **移动请求 (Move):** 向 API 提交修改父目录所属节点的请求，将整个包含 ISO 的父文件夹直接剪切到目标路径，实现最极致的高效整理。  
3. **删除请求 (Delete):** Python 标准库中提供了类似于 shutil.rmtree(path) 的高级封装方法用于递归清空目录树 7。在 115\_Helper 的架构中，系统通过原生 API 发送对该根目录标识符的 Delete 请求，实现一键穿透销毁，彻底释放网盘空间。

## **功能集二：扁平化媒体聚落的原地重构与降维归集**

在处理来自 P2P 网络、DMM 原档流出或特定影视合集时，用户经常会面临一种极度混乱的“扁平化文件聚落（Flat Directory）”现象。为了节省打包时间，发布者会将数十甚至数百个独立的媒体文件直接倾倒在一个庞大的父目录下（例如需求示例中的 上级多层路径/DMM原档 MNSE系列原档合集【291GB 64V】）。这种缺乏层级的结构对于 Kodi、Emby 或 Plex 这类高度依赖单文件单目录（One-Folder-Per-Movie）策略的刮削器来说是致命的，会导致大量的识别错误或刮削信息相互覆盖。

第二功能集旨在提供一套基于文本清洗和 API 并发调用的“重新归集”流水线，能够在 115 网盘服务端瞬间完成庞大目录树的构建与文件的归档操作。

### **用户定义的黑名单过滤器与字符串清洗引擎**

由于合集发布者往往会在视频文件命中插入诸如发布站网址、压制小组标签、分辨率标识等无关噪点字符（如 www.98T.la@、\_4Ks），如果直接使用当前文件名来创建目录，不仅丑陋且不利于后续的自动化元数据拉取。

因此，系统需集成一个“关键字黑名单（Keyword Blacklist Engine）”引擎。该引擎在后台以责任链模式对文件名进行多次迭代的字符串剥离操作。

**清洗流水线算法示例分析：**

以目标文件 www.98T.la@MNSE-030\_4Ks.mp4 为例，用户已配置黑名单数组 \`\`。

1. **扩展名剥离层:** 系统提取文件的基础名称（Basename），得到 www.98T.la@MNSE-030\_4Ks。  
2. **正则与全文替换层:** 引擎遍历黑名单规则。首先匹配并消除首部广告标识，变异为 MNSE-030\_4Ks；随后识别并消除尾部分辨率标识，最终坍缩为核心字符：MNSE-030。  
3. **冲突检测与修饰层:** 在处理数百个文件的过程中，清洗后的字符串极易出现同名现象。引擎必须在当前作用域内维护一个内存哈希表，一旦发现生成的目录名称（如 MNSE-030）发生哈希碰撞，将自动追加防冲突序列后缀（例如 MNSE-030 (1)，MNSE-030 (2)），确保新建目录路径的绝对唯一性。

经过这套清洗引擎的运算，这个核心字符将作为后续 API 操作的基准父目录名称。

### **目录结构的动态伸缩与并发归集**

在原生 Python 操作系统编程中，管理文件和目录的移动与创建依赖于 os 和 shutil 标准库 7。例如，shutil.move(src, dst) 提供文件位移 7，而自 Python 3.5 起引入的面向对象路径库 pathlib 提供了 pathlib.Path.mkdir(parents=True, exist\_ok=True) 这一极具鲁棒性的方法，它完美模拟了 Linux 系统中 mkdir \-p 的功能，能够在静默处理同名目录存在的情况下，递归创建多层级目录路径，极大地降低了 OSError 的捕获与处理成本 10。

115\_Helper 必须在云端 API 交互层级“复刻”这种高容错性、高可用性的代码范式。云端扁平媒体重构操作遵循以下四个生命周期：

1. **多视频探测与映射期 (Probe & Map):**  
   程序接收用户指定的“最终子目录”入口。调用 115 文件列表 API，获取该节点下所有的子实体。通过内置的视频扩展名列表（前文述及的矩阵 ![][image7]），过滤掉说明文档、种子文件等无关杂质，输出一份干净的视频文件清单与对应的云端文件 UUID 集合。  
2. **虚拟目录树构建期 (Virtual Tree Generation):**  
   系统在内存中针对该清单里的所有项目，执行上述的字符串黑名单清洗。在内存中勾勒出一幅预期需要生成的目录结构蓝图（即将创建 32 个独立的以番号命名的文件夹）。  
3. **云端目录实例化 (Instantiation):** 这里需要借鉴 mkdir(exist\_ok=True) 的逻辑 10。系统并不能盲目地下发创建指令。它首先查询当前父目录下是否已经存在清洗后的目录名。如果不存在，则通过 115 目录创建接口建立文件夹，并获取新产生的文件系统 ID（CID）。为了防止在高延迟网络环境下造成的性能衰减，此步骤建议在 p115client 的异步模式下通过协程池（Coroutine Pool）进行并发请求处理，大幅缩减 IO 等待时间 6。  
4. **极速下沉归集期 (Ingestion):**  
   当所有的纯净子目录实例化完毕并拿到了各自的云端 CID 后，系统再次调用 115 原生“移动” API。将原始视频文件（如 www.98T.la@MNSE-001.mp4）所属的节点 ID，批量更新至对应新创建的纯净目录（如 MNSE-001）的 CID 下。

得益于云存储系统底层的元数据管理机制，即便是面对总体积高达数百 GB（如示例中的 291GB 原档合集）的数据，整个由数十个文件的隔离、创建和重定向组成的重新归集过程，也仅需在数秒内即可在网盘服务端执行完毕。这展示了直接对接原生 API 在大规模媒体管理场景下的压倒性优势。

## **容器化持续运行与会话保活机制**

鉴于 115\_Helper 被定位为一款容器化部署（Dockerized）的网页软件，它需要在无人值守的服务器或 NAS 环境中长期驻留，为前端页面提供稳定、实时的 API 网关。云盘服务对第三方调用的限制不仅体现在接口速率上，更体现在会话令牌（Cookie / Token）的时效性上。常规的授权凭证往往在数天甚至数小时后失效，这会使得正在执行中的深度目录扫描与归集任务瞬间崩溃。

为了克服这一致命缺陷，底层架构必须设计一套自愈式的会话持久化与登录阻断恢复机制。

在服务启动时，容器通过挂载的本地卷读取持久化的 Cookie 文件（例如映射为 \~/115-cookies.txt 的路径）以初始化客户端实例 6。p115client 等高级封装框架提供了一种智能的自动重登录逻辑：在客户端初始化时设置开启 check\_for\_relogin=True 参数 6。

当后台引擎正在执行批量的“移动”或“秒传”任务时，如果 115 服务端突然拒载并抛出了表示鉴权失败或会话超时的 **HTTP 405 响应码** 6，115\_Helper 的网络拦截器将立即触发阻断机制。它会冻结当前操作队列中的所有异步协程，防止因连续的失败请求导致账号被风控。随后，引擎会自动向前端网页通过 WebSocket 下发一个告警事件，并生成扫码登录的二维码凭证。当管理员通过手机端应用完成扫码授权后，系统将捕获新的 Token 状态，自动将新凭证覆写回本地持久化的 Cookie 文件中，并在断点处平滑重启之前冻结的请求任务 6。

这种将异常处理下沉到框架底层，并在应用层提供无缝衔接的架构设计，确保了系统能在极度不稳定的公网网络环境下，安全、一致地执行 PB 级别的复杂媒体资产梳理动作。通过舍弃高耦合度的虚拟层，彻底拥抱原生的轻量级指针操作范式，115\_Helper 将极大限度地释放 115 云端算力，成为构建完美自动化个人流媒体中心的核心中间件。

#### **引用的著作**

1. CloudDrive2 gRPC API 开发者指南, 访问时间为 三月 31, 2026， [https://www.clouddrive2.com/api/CloudDrive2\_gRPC\_API\_Guide.html](https://www.clouddrive2.com/api/CloudDrive2_gRPC_API_Guide.html)  
2. Awhitedress AWdress \- GitHub, 访问时间为 三月 31, 2026， [https://github.com/AWdress](https://github.com/AWdress)  
3. GitHub \- deadblue/py115: A Python API SDK of 115 cloud storage., 访问时间为 三月 31, 2026， [https://github.com/deadblue/py115](https://github.com/deadblue/py115)  
4. johnnywsd/115-lixian: Unofficial Python API for 115 \- GitHub, 访问时间为 三月 31, 2026， [https://github.com/johnnywsd/115-lixian](https://github.com/johnnywsd/115-lixian)  
5. shichao-an/115wangpan: (Deprecated) Unofficial Python API wrapper SDK for 115.com (115网盘) \- GitHub, 访问时间为 三月 31, 2026， [https://github.com/shichao-an/115wangpan](https://github.com/shichao-an/115wangpan)  
6. ChenyangGao/p115client: Python 115 client · GitHub, 访问时间为 三月 31, 2026， [https://github.com/ChenyangGao/p115client](https://github.com/ChenyangGao/p115client)  
7. Python | Move or Copy Files and Directories \- GeeksforGeeks, 访问时间为 三月 31, 2026， [https://www.geeksforgeeks.org/python/python-move-or-copy-files-and-directories/](https://www.geeksforgeeks.org/python/python-move-or-copy-files-and-directories/)  
8. shutil — High-level file operations — Python 3.14.3 documentation, 访问时间为 三月 31, 2026， [https://docs.python.org/3/library/shutil.html](https://docs.python.org/3/library/shutil.html)  
9. File and Directory Management in Python: Move, Copy, Delete with Confidence \- Medium, 访问时间为 三月 31, 2026， [https://medium.com/@caring\_smitten\_gerbil\_914/file-and-directory-management-in-python-move-copy-delete-with-confidence-1b5dfb1e81be](https://medium.com/@caring_smitten_gerbil_914/file-and-directory-management-in-python-move-copy-delete-with-confidence-1b5dfb1e81be)  
10. mkdir \-p functionality in Python \[duplicate\] \- Stack Overflow, 访问时间为 三月 31, 2026， [https://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python](https://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python)

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA8AAAAYCAYAAAAlBadpAAAAnUlEQVR4XmNgGAUDB5YC8X8iMU6AT0E4EH9FF4QBEQaIxgNo4jDAA8SH0QVhIJ0BotkPSYyRAaIJBASBeCGSHAq4ygDRDFMMAhFAbANlMwMxB5IcCkD3Lx+Uz4IkhhXA/IuO/yErwgWw+VcGiLci8XECmH95kcQ8gdgFiY8ToPuXaEAofvGCcgaI5iB0CXxgJwNm6ILwcmRFo4AKAAC8Ki99XJzSaAAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA4AAAAYCAYAAADKx8xXAAAAiElEQVR4XmNgGAW0A2uA+D8JGA5AHAlkAagYiiIgEEYWUwLiKQg5MBBkgCg4jSYOAg9hDJAzOZEkQCCaAaIxCE0cZOBCGMcdSQIGQDaBNPKiiXMDsTSaGArA5j+CQIQBoukwugQhkM6A3X8EwVUG7P4jCOjrv2YGiEZQPBIEngwI52HDo4BUAABU6SzyHdISRAAAAABJRU5ErkJggg==>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAXCAYAAAA/ZK6/AAAAr0lEQVR4XmNgGAUYQB2I7wKxOboENhAOxO+BuBiI/wMxN6o0JgApmgTEn6BsvECQAaLIBl0CF/BkgGjgRZdAB7pAHALEhxggGkBsEGZFVoQMrBggCj4C8VcoG4QJApDpreiCuIA4A0SDMboELhDEANHAgS6BC6xhICLckQEookDJgWhAkodhMayJLoEOIoE4AIj9GIhwPw8DRNFbIN4BxM2o0tgBSMMGIH6ELkExAACo8yJEYb3EhgAAAABJRU5ErkJggg==>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACIAAAAYCAYAAACfpi8JAAABI0lEQVR4XmNgGAWjYBQMLHgExH+B+D8UPwFieRQVDAznoHIgDFKbhCpNPaDEALHkAJo4MrjOgOlArIAHiEOAeBYSLkRRgRuA9MJCAxswBOLN6ILoQIEBYkgVEAujSpEEYEGPDYDEGdEFkYE3EJ9GFyQT4HLIBCB2RRdEBiAXfkUXpACAzAI5hAVJDBRlz5D4WEE6EBujC1IAQCELcogkkhjIESDH4AV7gFiKAaIRFyYlzSxkgDjEFMr3A+JmhDRuQG2HgEIY5JAiBki0/0OVxg1AGi3RBSkAoGgGOQQUMruAWBtVGjegdmIVZ4A45AcQH0KTIwjMGKiXfUEeg2VhvGUGLiDDANFcA8RiaHKkApA5weiCpAJYEV/GQHoRPwpGAU0AAM/rOX2Rj1/HAAAAAElFTkSuQmCC>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADMAAAAYCAYAAABXysXfAAABsUlEQVR4Xu2WTytFURTFt6LInxJlYkJKBkaSiKGBlAHKVzBm4BP4AjKSmUwwk7mMjIwoJTOlSKIoGbCX866e9c453tn39kb3V6tua9/93j5/9jlXpKSkpCTAsOpWNcEBIx2qAzYbwYrqWbWu+lK1/w2bOFe1sRmgW9z/1qs1l+YHL2ypXivPeelRHbMZAf+9R96muFqmyX9QjZH3SzYrnJSHS6l/VcAnG8q9uLqayT8Vt4W9zIlL6uSAkT5J6xVM5jab4mp6Z1PcIGsYVS2rzsQl4hlqqX7JwI2k/Uav1K7ioLia9skH82yAKXHFv6jeKs9QHgZUu2wayPplnAP/gaQjNiP0q3YCwqRgMOw3/WTWz5O4upLycAQjaZEDBobEv/cthPolCo44JKJp8/IoiTMZYETC/RIl25sp+LbZoerC42fi4zUG7hxTv1yJYTk9oFeKwtQvAEknbCaCrbrBphEc6ajJd4lGwdIjcYEDiXywYQB1hDRZ9V6QrNFaOZDAjGqVzUaCAWBfovnvKJZK8nYoEnygYTD41Mf2wMlkZVaKuZ9ysaS6VnVxIBHcKyVF8A1iCWyNOWnYigAAAABJRU5ErkJggg==>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAXCAYAAAAC9s/ZAAAAt0lEQVR4XmNgGAWDAwgD8SMg/o+EQXx08I4BIQ9ii6FKMzC0MkAkfdElkABInhFdEAZAGkEKqtAloGA6ELuiCyIDTQaIAXvQJRgg3ryLLogOeBggBjxElwCC10DMiS6IDYAM+I0mFgTEzWhiOAEslGHAHIjnI/EJgicMEANA3gGBf0hyRIEDDBADlBggNtuiyBIBYGkhFYivo8kRBWBpAYRZ0eSIArC0UIwuQSzgAOKr6IKjAD8AAG5pJsEBCna+AAAAAElFTkSuQmCC>
