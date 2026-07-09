<div align="center">

# ICESat-2 浅海测深工具
### ICESat-2 Shallow Water Bathymetry Tool (SDAF)

**基于 ICESat-2 ATL03 激光测高光子点云的浅海水深提取与海底地形反演软件**

一站式完成:水面识别 → SDAF 自适应去噪 → 水下折射改正 → 海底地形拟合 → 多光谱水深反演

*水面高程计算 · 尺寸/方向自适应滤波 (SDAF) · 折射改正 · 地形建模 · 机器学习水深预测*

<img width="1080" height="720" alt="image" src="https://github.com/user-attachments/assets/39d4a49c-79f0-428a-b6d9-7e9a5ff79bf9" />

图形界面 | 命令行 | Python API | 批处理 | Windows 一键打包

</div>

---

## 📖 项目简介

**ICESat-2 浅海测深工具**是一款面向海洋测绘、海岸带遥感与水下地形研究的桌面软件。它以 NASA ICESat-2 卫星的 **ATL03 全球地理定位光子产品(HDF5)** 为输入,复现并改进了经典论文中的 **SDAF(Size and Direction Adaptive Filtering,尺寸/方向自适应滤波)** 浅海测深方法,自动从高噪声的原始光子点云中提取水面、分离水下信号光子、进行折射改正,最终生成沿轨水深剖面与海底地形线;并可进一步结合多光谱遥感影像,用机器学习模型将稀疏的沿轨测深点扩展为**面状水深图**。

软件同时提供:

- 🖥️ **图形界面(GUI)**——iOS 风格界面,交互式出图、在线卫星底图联动、光子悬停查询;
- ⌨️ **命令行脚本**——`main.py` 一条命令跑通全流程;
- 🐍 **Python 批处理 API**——`api.py` 支持多文件 × 多波束全自动处理;
- 📦 **Windows 打包套件**——PyInstaller + Inno Setup,一键生成绿色版和安装包。

> 适用人群:海洋测绘 / 摄影测量与遥感 / 海岸工程方向的科研人员、研究生,以及需要快速获取浅海水深数据的工程用户。

---

## ✨ 功能特性

### 核心处理流程(四步法)

| 步骤 | 模块 | 功能说明 |
|------|------|----------|
| **Step 0** | `h5_to_csv.py` | 从 ATL03 (.h5) 中抽取任一波束(gt1l/gt1r/gt2l/gt2r/gt3l/gt3r)的光子点云,展开分段几何信息,输出统一 CSV(经纬度、椭球高、沿轨距离、海洋置信度、参考高度角等) |
| **Step A** | `step_a_water_surface.py` | **水面高程计算**:高程直方图 + 高斯拟合确定瞬时水面,沿轨分段追踪水面剖面,将光子分类为水上/水面/水下三类 |
| **Step B** | `step_b_sdaf.py` | **SDAF 自适应去噪**:变尺寸椭圆核(随水深自适应放大)+ 变方向旋转(−60°~60°)统计邻域密度,密度直方图双高斯拟合自动定阈值分离信号/噪声,再经分段二次拟合迭代剔除残余噪声 |
| **Step C** | `step_c_refraction.py` | **折射改正**:基于光线入射角与水体折射率(默认 n₂=1.34),对水下信号光子逐点做位置与深度改正,输出每个光子的真实水深 |
| **Step D** | `step_d_terrain.py` | **海底地形拟合**:海平面与海底剖面稳健滑动多项式拟合,输出等间距海底地形线节点(含改正前/后对比),自动识别地形间断、剔除超限异常深度 |

### 对论文方法的关键改进

原论文中椭圆核尺寸由"光子自身深度"决定,在高噪声真实数据中,深处噪声光子会获得过大的椭圆而被误判为信号("信号铺满整个水柱")。本软件的改进:

- **以当地海底水深定椭圆**(`SIZE_BY="seabed"`):先粗估沿轨海底深度剖面,再用该位置的海底深度决定椭圆大小,远低于海底的噪声光子只能获得小椭圆,从而被正确剔除;
- **海底带细化**:最后将信号收敛为一条干净的海底线,解决"海底连不成线"的问题;
- 保留论文字面实现(`SIZE_BY="photon"`)作为可选项,便于方法对比。

### 多光谱水深反演(水深预测)

`depth_inversion.py` 模块可将 ICESat-2 沿轨测深点作为训练样本,结合多光谱遥感影像(GeoTIFF 栅格),用机器学习方法反演**面状水深图**:

- 支持 **随机森林(Random Forest)、支持向量回归(SVR)、K 近邻(KNN)、线性回归** 等多种模型;
- 自动划分训练/验证集,输出 RMSE、R² 等精度指标;
- 结果可导出为栅格/图片,并生成基于 folium 的交互式网页地图。

### 图形界面(GUI)亮点

- 🎨 **iOS 风格界面**:左侧功能按钮(输入 / 参数 / 运行 / 分类 / 批处理 / 帮助),弹窗式操作;
<img width="1432" height="993" alt="屏幕截图 2026-06-27 221302" src="https://github.com/user-attachments/assets/3ab7ec15-202c-4d2d-8826-5674f8922254" />
- 📊 **交互式结果图**:每一步的"活"结果图带缩放/平移/复位/保存工具条;鼠标悬停到任意光子即高亮并显示经纬度、高程、水深;
<img width="1284" height="888" alt="屏幕截图 2026-06-27 221605" src="https://github.com/user-attachments/assets/1e48316c-931c-4c0f-873f-8f65612f8c84" />
- 🗺️ **在线卫星底图联动**:右下角 Web 底图(默认 Google 卫星,可切换),与结果图**双向联动高亮**(基于 blit 渲染,不卡顿);滚轮缩放、拖动平移,松手自动按范围重取瓦片;
<img width="1789" height="1241" alt="屏幕截图 2026-06-20 213100" src="https://github.com/user-attachments/assets/99b365a8-727b-4f92-92d8-144f47efce2d" />
- 📈 **实时进度与日志**:进度条 + 运行用时 + 滚动日志;
<img width="1789" height="1241" alt="屏幕截图 2026-06-20 213100" src="https://github.com/user-attachments/assets/8b7df635-55dc-4083-8b7e-807da1ee8397" />
- ⚡ **大数据自动抽样显示**:显示层按需抽样保证流畅,**处理与导出仍使用全量数据**;
<img width="1799" height="1242" alt="屏幕截图 2026-06-27 222343" src="https://github.com/user-attachments/assets/97a7e94d-1b02-4740-8826-33f78e9dd987" />
- 💾 **每步可导出**:各阶段结果图(PNG)与数据(CSV)均可单独保存。

### 数据批处理
<img width="1799" height="1242" alt="屏幕截图 2026-06-27 222343" src="https://github.com/user-attachments/assets/ae04d26b-9dff-42aa-9a93-90555ec4f17b" />

- 两种模式:**多波束处理**(1 个文件 × 勾选任意波束)与**文件夹处理**(整个文件夹的所有 .h5/.csv × 所有勾选波束);
- 后台线程运行,进度/日志实时回传,可安全中止;
- 支持按 **经纬度范围(bbox)** 或 **Shapefile 边界** 裁剪研究区;
- 一键将本次全部测深点**合并导出为单个 CSV 或 SHP**,方便直接进入 GIS 软件。

### Python API(激活后可用)

```python
import api

# 单文件、单波束
res = api.process("ATL03_xxx.h5", beam="gt1l", outdir="out_1l")
print(res["summary"])          # 各阶段统计
print(res["water_depth_csv"])  # 水深结果 CSV 路径

# 批处理:多文件 × 多波束 + 研究区裁剪 + 参数覆盖
summary = api.batch(
    inputs=["a.h5", "b.h5"],
    beams=["gt1l", "gt2r"],
    outdir="batch_out",
    crop={"mode": "bbox", "lon_min": -64.9, "lon_max": -64.7,
          "lat_min": 17.7, "lat_max": 17.8},
    params={"A_K_SIGMA": 3.0, "C_N2": 1.34},
)
```

---

## 🖼️ 输出成果

运行全流程后,输出目录将包含:

| 文件 | 内容 |
|------|------|
| `step_a_water_surface.png` | 水面识别结果图 |
| `step_b_density_hist.png` | 光子密度直方图 + 双高斯拟合 + 自动阈值 |
| `step_b_denoise.png` | SDAF 三阶段去噪对比图 |
| `step_c_refraction.png` | 折射改正前后对比(论文配色) |
| `step_d_terrain.png` | 海平面/海底地形拟合(改正前后) |
| `overview.png` | 全流程总览图 |
| `photons_classified.csv` | Step A 光子分类结果 |
| `underwater_sdaf.csv` | Step B 密度与信号标记 |
| `signal_refraction.csv` | Step C 逐光子结果(含 `water_depth` 水深列) |
| `bottom_terrain_line.csv` | Step D 海底地形线节点(含 `water_depth` 水深列) |

---

## 🚀 快速开始

### 环境要求

- **操作系统**:Windows 10/11(64 位,推荐);源码在其他平台亦可运行核心流程
- **Python**:3.11(64 位)
- **网络**:在线底图与瓦片下载需联网;核心测深流程可完全离线

### 安装

```bash
git clone https://github.com/<your-name>/ICESat2Bathy.git
cd ICESat2Bathy
python -m pip install -r requirements.txt
```

主要依赖:`numpy` `pandas` `scipy` `matplotlib` `h5py` `scikit-learn`(科学计算);`geopandas` `rasterio` `shapely` `pyproj` `fiona` `folium` `contextily`(地理空间与底图);`PyQt5` + `PyQtWebEngine`(水深预测窗口与网页地图)。

### 使用方式一:图形界面(推荐)

```bash
python gui_app.py
```

1. 点击 **输入**,选择 ATL03 `.h5`(或已转换的 `.csv`),选择波束,可选设置裁剪范围;
2. 点击 **参数**,按需调整各步骤参数(均有默认值,一般无需修改);
3. 点击 **运行**,查看每一步的实时结果图与日志;
4. 在结果图上悬停查看单光子信息,与卫星底图联动定位;
5. 各步骤结果图/数据可随时保存;需要面状水深图时打开 **水深预测** 窗口。

### 使用方式二:命令行脚本

```bash
# 可选:先把 h5 抽取为 csv(也可直接在 main.py 里用 h5)
python h5_to_csv.py ATL03_xxx.h5 --beam gt2r --out my_area.csv
python h5_to_csv.py ATL03_xxx.h5 --beam gt2r --lat-min 17.75 --lat-max 17.81

# 修改 main.py 顶部 CONFIG 中的输入路径与参数后运行全流程
python main.py
```

### 使用方式三:Python API 批处理

见上文 [Python API](#python-api激活后可用) 示例。

---

## ⚙️ 参数说明(节选)

所有参数均有推荐默认值,GUI 的"参数"面板与 `api.DEFAULT_PARAMS` 完全一致:

| 参数 | 含义 | 默认值 |
|------|------|--------|
| `A_BIN_WIDTH` | 高程直方图分辨率 (m) | 0.2 |
| `A_K_SIGMA` | 水面带半宽 k×σ | 3.0 |
| `A_SEG_LEN` | 沿轨分段长 (m) | 300 |
| `B_A0` | 椭圆基础长半轴 a₀ (m) | 10 |
| `B_K_SIZE` | 长半轴随深度系数 | 2.5 |
| `B_B_RATIO` | 短/长半轴比 | 0.1 |
| `B_THETA_RANGE` / `B_THETA_STEP` | 旋转角范围 / 步长 (°) | (−60, 60) / 10 |
| `B_SIZE_BY` | 定椭圆方式:`seabed`(改进)/`photon`(论文) | `seabed` |
| `C_N1` / `C_N2` | 空气 / 水折射率 | 1.0 / 1.34 |
| `D_GRID_STEP` | 地形线节点间距 (m) | 25 |
| `D_MAX_DEPTH` | 最大水深阈值 (m,超限剔除) | 60 |

---

## 📁 项目结构

```
ICESat2Bathy/
├── gui_app.py               # 图形界面主程序(入口)
├── gui_helpers.py           # GUI 通用组件(iOS 风格控件、底图、blit 高亮等)
├── main.py                  # 命令行全流程脚本(入口)
├── h5_to_csv.py             # Step 0: ATL03 HDF5 → CSV 转换器
├── step_a_water_surface.py  # Step A: 水面高程计算与光子分类
├── step_b_sdaf.py           # Step B: SDAF 尺寸/方向自适应滤波去噪
├── step_c_refraction.py     # Step C: 水下折射改正
├── step_d_terrain.py        # Step D: 海平面/海底地形稳健拟合
├── depth_inversion.py       # 水深预测: 多光谱 + 机器学习水深反演(PyQt5 窗口)
├── api.py                   # Python 批处理接口
├── batch_dialog.py          # GUI 数据批处理窗口
├── licensing.py             # 离线授权 + 试用额度管理
├── license_dialog.py        # 授权/购买对话框
├── utils.py                 # 中文字体等工具函数
├── rthook_geo.py            # PyInstaller 运行时钩子(SSL 证书 / 地理库路径)
├── requirements.txt         # 依赖清单
├── ICESat2Bathy.spec        # PyInstaller 打包配置
├── build.bat                # 一键打包脚本(绿色版)
├── installer.iss            # Inno Setup 安装包脚本
├── licenses/                # 第三方开源组件许可证
└── 打包说明.txt              # 详细打包与常见问题指南
```

---

## 📦 打包为 Windows 安装包

本仓库即"可直接打包"的工程,在 Windows 上三步完成:

1. 安装 **Python 3.11(64 位)**(勾选 *Add python.exe to PATH*)和 **Inno Setup 6**(仅做安装包需要);
2. 双击 `build.bat` —— 自动安装依赖、清理旧文件、PyInstaller 打包,产物在 `dist\ICESat2Bathy\ICESat2Bathy.exe`(绿色免安装版);
3. 右键 `installer.iss` → *Compile*,在 `Output\` 得到正式安装包 `ICESat2Bathy_Setup_x.x.x.exe`。

打包套件已内置修复:fiona ≥1.9 子模块变更导致的 `ModuleNotFoundError`、打包后 SSL 证书缺失导致底图空白(`rthook_geo.py` 自动指向随包 certifi 证书)等。更多细节与常见问题见 `打包说明.txt`。

> 💡 排错技巧:将 `ICESat2Bathy.spec` 中 `console=False` 临时改为 `True` 重新打包,即可在控制台看到详细启动报错。

---

## 🔑 授权与试用

- **免费试用**:可免费处理 **3 个文件**(一个文件 = 一条数据 + 波束 + 裁剪范围的完整流程);同一条数据重复运行、保存图片/数据**不重复计数**;
- **永久授权**:采用**离线"机器码 + 授权码"**方案 —— 软件根据本机硬件生成唯一机器码,联系作者（1454004559@qq.com）获取绑定该机器码的授权码,填入即永久激活,全程无需联网;
- 授权码基于 HMAC-SHA256 生成,与机器绑定,拷贝授权文件到其他电脑无效;
- **批处理窗口与 Python API 需激活后使用**。

购买与授权咨询:微信公众号 **遥感小屋**。

---

## ❓ 常见问题(FAQ)

**Q:打开软件后右下角地图空白?**
A:在线底图(Google/Esri/OSM 瓦片)需要联网;公司/校园网防火墙可能屏蔽 Google 瓦片,可在设置中切换底图源。

**Q:杀毒软件报毒?**
A:PyInstaller 打包的 exe 偶有误报,添加信任即可;正式分发建议做代码签名。

**Q:支持哪些输入数据?**
A:ICESat-2 **ATL03**(.h5,可从 [NASA Earthdata](https://search.earthdata.nasa.gov/) 免费下载)或本工具转换/兼容格式的 CSV;水深预测模块另需多光谱 GeoTIFF 影像。

**Q:水深结果的参考基准是什么?**
A:光子高程为 WGS84 椭球高;水深列 `water_depth` 为折射改正后信号光子相对瞬时水面的深度。

---

## 📚 方法参考

本软件的核心流程复现自 SDAF 浅海测深论文的 *II. METHODOLOGY* 三步法(水面高程计算 → SDAF 去噪 → 折射改正),并在椭圆核尺寸策略与海底带细化上做了针对高噪声真实数据的稳健性改进;水深反演模块的机器学习框架参考了开源项目(MIT 协议,详见源码内声明)。

> 若本工具对你的研究有帮助,请在论文中引用相应的 SDAF 原始文献及 ICESat-2 ATL03 数据来源。

---

## 📄 许可证

本软件以打包应用形式分发,**版权归作者所有(All rights reserved)**。所依赖的第三方开源组件(NumPy、Pandas、SciPy、scikit-learn、GeoPandas、Rasterio 等)遵循各自的开源许可证,详见 [`licenses/`](licenses/) 目录。

---

## 📮 联系作者

- 微信公众号:**遥感小屋**
- 问题反馈:欢迎提交 [Issue](../../issues)

<div align="center">

**如果这个项目对你有帮助,欢迎点亮 ⭐ Star!**

</div>
