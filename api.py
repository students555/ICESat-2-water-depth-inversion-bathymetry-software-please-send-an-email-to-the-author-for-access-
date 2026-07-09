# -*- coding: utf-8 -*-
"""
api.py -- 数据批处理调用接口(对应需求⑥, 激活后可用)
=====================================================================
缴费激活后, 可在 Python 脚本里调用本模块对一批 .h5 / .csv 数据做全自动处理
(Step A 水面识别 → B SDAF 去噪 → C 折射改正 → D 海底地形拟合),
无需打开图形界面。未激活时调用会抛出 LicenseError。

最简用法
--------
    import api
    # 单文件、单波束:
    res = api.process("ATL03_xxx.h5", beam="gt1l", outdir="out_1l")
    print(res["summary"])          # 各阶段统计
    print(res["water_depth_csv"])  # 水深结果 CSV 路径

    # 批处理: 多文件 × 多波束:
    summary = api.batch(
        inputs=["a.h5", "b.h5"],
        beams=["gt1l", "gt2r"],
        outdir="batch_out",
        crop={"mode": "bbox", "lon_min": -64.9, "lon_max": -64.7,
              "lat_min": 17.7, "lat_max": 17.8},  # 可选裁剪, 不裁剪用 None
        params={"A_K_SIGMA": 3.0, "C_N2": 1.34},  # 可选: 覆盖默认参数
    )
    for row in summary:
        print(row["input"], row["beam"], row["status"], row.get("n_signal"))

参数说明: 默认参数见 DEFAULT_PARAMS, 可用 params=dict(...) 局部覆盖。
裁剪 crop: {"mode":"none"} / {"mode":"bbox", lon_min/lon_max/lat_min/lat_max} /
           {"mode":"shp", "path":"xxx.shp"}。
"""
import os
import time
import json
import pandas as pd

import licensing
from step_a_water_surface import run_step_a
from step_b_sdaf import run_step_b
from step_c_refraction import run_step_c
from step_d_terrain import run_step_d


class LicenseError(RuntimeError):
    """未激活/未授权时调用批处理接口抛出。"""


DEFAULT_PARAMS = {
    # Step A
    "A_BIN_WIDTH": 0.2, "A_FIT_HALFWIDTH": 3.0, "A_K_SIGMA": 3.0,
    "A_SEG_LEN": 300.0, "A_DRIFT_TOL": 5.0, "A_SIGMA_CAP": 1.0,
    # Step B
    "B_A0": 10.0, "B_K_SIZE": 2.5, "B_B_RATIO": 0.1,
    "B_THETA_RANGE": (-60, 60), "B_THETA_STEP": 10, "B_SEG_LEN": 200.0,
    "B_QFIT_THRESH": (20.0, 10.0, 5.0), "B_QFIT_LOOP": 3,
    "B_SIZE_BY": "seabed", "B_BOTTOM_BIN_LEN": 100.0,
    "B_BOTTOM_MIN_DEPTH": 1.0, "B_DEPTH_CAP": None, "B_BAND_HALFWIDTH": 3.0,
    # Step C
    "C_N1": 1.0, "C_N2": 1.34,
    # Step D
    "D_GRID_STEP": 25.0, "D_SURF_WINDOW": 500.0, "D_SURF_DEGREE": 1,
    "D_BOTTOM_WINDOW": 300.0, "D_BOTTOM_DEGREE": 2, "D_MIN_PTS": 8,
    "D_ROBUST_ITER": 2, "D_MAX_DEPTH": 60.0, "D_MAX_GAP": None,
}


def _require_license():
    if not licensing.is_activated():
        raise LicenseError(
            "批处理接口仅在激活永久授权后可用。请先在图形界面‘购买授权’完成激活, "
            "或联系作者(微信公众号:遥感小屋)获取授权码。")


def _load_df(input_path, beam, crop):
    from h5_to_csv import apply_crop
    if input_path.lower().endswith(".csv"):
        df = pd.read_csv(input_path)
    else:
        from h5_to_csv import read_atl03_beam
        df = read_atl03_beam(input_path, beam)
    df = apply_crop(df, crop or {"mode": "none"}).reset_index(drop=True)
    if not {"lat", "lon", "h", "x_atc"}.issubset(df.columns):
        raise ValueError("数据需含 lat/lon/h/x_atc 列")
    if len(df) == 0:
        raise ValueError("裁剪后没有任何光子, 请检查裁剪范围")
    return df


def process(input_path, beam="gt1l", outdir="results", crop=None,
            params=None, make_plots=True, verbose=True,
            file_prefix=None, save_all_csv=True):
    """处理单个文件的单条波束, 返回结果字典(含输出 CSV/PNG 路径与统计)。

    新增(供 GUI‘数据批处理’使用, 默认行为完全兼容旧调用):
      file_prefix : 不为 None 时, 所有输出文件名加前缀(如 "ATL03xxx_gt1l_"),
                    并直接写入 outdir(不再建子文件夹) —— 满足
                    ‘原数据名 + 条带名 + 阶段’ 的命名要求。
      save_all_csv: False 时只保留 water_depth / bottom_terrain_line 两个关键 CSV,
                    其余中间 CSV 处理后删除(节省空间)。
    """
    _require_license()
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)
    cfg = dict(DEFAULT_PARAMS)
    if params:
        cfg.update(params)
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()

    pfx = file_prefix or ""

    def _png(name):
        return os.path.join(outdir, pfx + name) if make_plots else None

    def _csv(name):
        return os.path.join(outdir, pfx + name)

    df = _load_df(input_path, beam, crop)

    # Step A
    df, surf = run_step_a(
        df, out_png=_png("step_a_water_surface.png"),
        bin_width=cfg["A_BIN_WIDTH"], fit_halfwidth=cfg["A_FIT_HALFWIDTH"],
        k_sigma=cfg["A_K_SIGMA"], seg_len=cfg["A_SEG_LEN"],
        drift_tol=cfg["A_DRIFT_TOL"], sigma_cap=cfg["A_SIGMA_CAP"], verbose=verbose)
    classified_csv = _csv("photons_classified.csv")
    df.to_csv(classified_csv, index=False)

    under = df[df["cls"] == "under"].reset_index(drop=True)
    if len(under) < 5:
        raise RuntimeError("水下光子过少, 无法执行 SDAF。请检查裁剪范围/数据。")

    # Step B
    under, binfo = run_step_b(
        under, surf["mu"],
        out_prefix=(os.path.join(outdir, pfx + "step_b") if make_plots else None),
        a0=cfg["B_A0"], k_size=cfg["B_K_SIZE"], b_ratio=cfg["B_B_RATIO"],
        theta_range=tuple(cfg["B_THETA_RANGE"]), theta_step=cfg["B_THETA_STEP"],
        seg_len=cfg["B_SEG_LEN"], qfit_thresholds=tuple(cfg["B_QFIT_THRESH"]),
        qfit_max_loop=cfg["B_QFIT_LOOP"], show_progress=False, size_by=cfg["B_SIZE_BY"],
        bottom_bin_len=cfg["B_BOTTOM_BIN_LEN"], bottom_min_depth=cfg["B_BOTTOM_MIN_DEPTH"],
        depth_cap=cfg["B_DEPTH_CAP"], band_halfwidth=cfg["B_BAND_HALFWIDTH"])
    sdaf_csv = _csv("underwater_sdaf.csv")
    under.to_csv(sdaf_csv, index=False)

    # Step C
    sig = under[under["sig_final"]].reset_index(drop=True)
    sig_corr = run_step_c(
        sig, surf["mu"], out_png=_png("step_c_refraction.png"),
        n1=cfg["C_N1"], n2=cfg["C_N2"], verbose=verbose)
    sig_corr["water_depth"] = sig_corr["depth_corr"]
    signal_csv = _csv("signal_refraction.csv")
    sig_corr.to_csv(signal_csv, index=False)

    # Step D
    surface_pts = df[df["cls"] == "surface"].reset_index(drop=True)
    terrain_csv = _csv("bottom_terrain_line.csv")
    terrain = run_step_d(
        sig_corr, surface_pts, surf["mu"],
        out_png=_png("step_d_terrain.png"), out_csv=terrain_csv,
        grid_step=cfg["D_GRID_STEP"], surf_window=cfg["D_SURF_WINDOW"],
        surf_degree=cfg["D_SURF_DEGREE"], bottom_window=cfg["D_BOTTOM_WINDOW"],
        bottom_degree=cfg["D_BOTTOM_DEGREE"], min_pts=cfg["D_MIN_PTS"],
        robust_iter=cfg["D_ROBUST_ITER"], max_depth=cfg["D_MAX_DEPTH"],
        max_gap=cfg["D_MAX_GAP"], verbose=verbose)

    # 水深结果(经纬度/高程/折射前后水深)
    wd = pd.DataFrame({
        "lon": sig_corr["lon"] if "lon" in sig_corr else float("nan"),
        "lat": sig_corr["lat"] if "lat" in sig_corr else float("nan"),
        "height_h": sig_corr["h"],
        "depth_before_refraction": sig_corr["depth_app"],
        "depth_after_refraction": sig_corr["depth_corr"],
    })
    wd_path = _csv("water_depth.csv")
    wd.to_csv(wd_path, index=False)

    # 仅保留关键 CSV(可选)
    if not save_all_csv:
        for p in (classified_csv, sdaf_csv, signal_csv):
            try:
                os.remove(p)
            except Exception:
                pass

    elapsed = time.time() - t0
    summary = {
        "input": input_path, "beam": beam, "outdir": os.path.abspath(outdir),
        "n_photons": int(len(df)), "n_under": int(len(under)),
        "n_signal": int(len(sig_corr)), "n_terrain_nodes": int(len(terrain)),
        "surface_mu": float(surf["mu"]), "elapsed_s": round(elapsed, 2),
        "status": "ok",
    }
    return {
        "summary": summary,
        "classified_csv": classified_csv,
        "sdaf_csv": sdaf_csv,
        "signal_csv": signal_csv,
        "terrain_csv": terrain_csv,
        "water_depth_csv": wd_path,
        "dataframes": {"classified": df, "signal": sig_corr, "terrain": terrain},
    }


def batch(inputs, beams=None, outdir="batch_results", crop=None,
          params=None, make_plots=True, verbose=False):
    """批处理: 对 inputs(文件列表) × beams(波束列表) 全组合逐个处理。
    返回每个组合的统计列表; 单个失败不影响其余(记 status='error')。"""
    _require_license()
    if isinstance(inputs, str):
        inputs = [inputs]
    if beams is None:
        beams = ["gt1l"]
    if isinstance(beams, str):
        beams = [beams]
    os.makedirs(outdir, exist_ok=True)
    results = []
    for ip in inputs:
        stem = os.path.splitext(os.path.basename(ip))[0]
        for bm in beams:
            sub = os.path.join(outdir, f"{stem}_{bm}")
            try:
                res = process(ip, beam=bm, outdir=sub, crop=crop,
                              params=params, make_plots=make_plots, verbose=verbose)
                results.append(res["summary"])
            except Exception as e:
                results.append({"input": ip, "beam": bm, "outdir": os.path.abspath(sub),
                                "status": "error", "error": str(e)})
    # 汇总表
    try:
        pd.DataFrame(results).to_csv(os.path.join(outdir, "batch_summary.csv"), index=False)
    except Exception:
        pass
    return results


def list_data_files(folder, recursive=False, exts=(".h5", ".csv")):
    """列出文件夹中的数据文件(.h5 / .csv)。recursive=True 时递归子文件夹。"""
    exts = tuple(e.lower() for e in exts)
    out = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for fn in files:
                if fn.lower().endswith(exts):
                    out.append(os.path.join(root, fn))
    else:
        for fn in os.listdir(folder):
            p = os.path.join(folder, fn)
            if os.path.isfile(p) and fn.lower().endswith(exts):
                out.append(p)
    return sorted(out)


def batch_folder(folder, beams=None, outdir="batch_results", recursive=False,
                 crop=None, params=None, make_plots=True, verbose=False,
                 exts=(".h5", ".csv")):
    """批处理整个文件夹: 自动扫描 folder 下的 .h5/.csv 并逐个跑全流程。
    返回每个(文件×波束)的统计列表; 单个失败不影响其余。需先激活。"""
    _require_license()
    if not os.path.isdir(folder):
        raise NotADirectoryError(folder)
    files = list_data_files(folder, recursive=recursive, exts=exts)
    if not files:
        raise FileNotFoundError(f"文件夹中未找到 {exts} 数据文件: {folder}")
    return batch(files, beams=beams, outdir=outdir, crop=crop,
                 params=params, make_plots=make_plots, verbose=verbose)


# ==========================================================================
# 接口使用说明 + 可运行示例脚本(供 GUI"批处理接口"按钮展示 / 导出)
# ==========================================================================
USAGE_DOC = r"""# ICESat-2 浅海测深工具 — 批处理接口使用说明

> 本接口在【缴费激活永久授权后】可用。未激活调用会抛出 api.LicenseError。
> 软件只提供"处理接口"; 具体在哪个文件夹、处理哪些文件、处理完怎么用,
> 都由你自己写脚本调用接口来完成。

## 0. 准备
- 接口位于 api.py。把软件全部 .py 文件(api.py / licensing.py / step_*.py /
  h5_to_csv.py / utils.py 等)放在同一目录, 或确保它们在 Python 可导入路径中。
- 依赖: numpy、pandas、scipy、matplotlib、h5py(读 .h5 需要)。
- 在该机器上已用主程序"购买授权"激活过(授权状态保存在本机, 接口会自动读取)。

## 1. 三个核心函数

### api.process(input_path, beam="gt1l", outdir="results", crop=None,
###             params=None, make_plots=True, verbose=True)
处理"单个文件的单条波束", 跑完 A→B→C→D 全流程, 写出 CSV/PNG, 返回结果字典:
  res["summary"]          各阶段统计(光子数/信号数/水面高程/耗时...)
  res["water_depth_csv"]  水深结果 CSV 路径(经纬度/高程/折射前后水深)
  res["terrain_csv"]      海底地形线 CSV 路径
  res["dataframes"]       内存中的 DataFrame: classified / signal / terrain

### api.batch(inputs, beams=None, outdir="batch_results", crop=None,
###           params=None, make_plots=True, verbose=False)
处理"文件列表 × 波束列表"的所有组合。inputs 可为单个路径或路径列表;
beams 缺省为 ["gt1l"]。返回每个组合的统计 dict 列表, 并写出 batch_summary.csv。
单个组合出错不影响其余(该行 status="error", 含 error 信息)。

### api.batch_folder(folder, beams=None, outdir="batch_results",
###                  recursive=False, crop=None, params=None,
###                  make_plots=True, verbose=False, exts=(".h5",".csv"))
直接批处理"一个文件夹": 自动扫描该文件夹(recursive=True 则含子文件夹)下的
所有 .h5/.csv, 等价于 api.batch(扫描到的文件列表, ...)。

## 2. 可选参数

### 波束 beams
"gt1l"/"gt1r"/"gt2l"/"gt2r"/"gt3l"/"gt3r" 中的任意一个或多个(r 波束信号通常更好)。

### 裁剪 crop(默认不裁剪)
  {"mode": "none"}                                                  # 不裁剪
  {"mode": "bbox", "lon_min":..,"lon_max":..,"lat_min":..,"lat_max":..}  # 经纬度框
  {"mode": "shp", "path": "aoi.shp"}                                # shp 多边形(WGS84)

### 参数覆盖 params(默认见 api.DEFAULT_PARAMS, 只需写要改的项)
例: params={"A_K_SIGMA": 3.0, "C_N2": 1.34, "D_MAX_DEPTH": 40.0}

### make_plots
False 时不输出 PNG, 只出 CSV(批处理大量文件时更快)。

## 3. 示例

### 示例 A — 一行批处理整个文件夹(最简单)
    import api
    rows = api.batch_folder(r"D:\\icesat2\\data", beams=["gt1l", "gt2r"],
                            outdir=r"D:\\icesat2\\out", make_plots=False)
    for r in rows:
        print(r["input"], r["beam"], r["status"], r.get("n_signal"))

### 示例 B — 自己写循环, 逐个处理并做自定义后处理(你的代码、你的流程)
    import os, glob, api, pandas as pd

    folder = r"D:\\icesat2\\data"
    files = glob.glob(os.path.join(folder, "*.h5"))   # 你自己决定要处理哪些

    all_depth = []
    for f in files:
        try:
            res = api.process(f, beam="gt2r",
                              outdir=os.path.join("out", os.path.basename(f)),
                              make_plots=False, verbose=False)
            df = pd.read_csv(res["water_depth_csv"])
            df["source_file"] = os.path.basename(f)
            all_depth.append(df)                       # 你自己的后处理: 汇总
            print("OK:", f, res["summary"]["n_signal"], "信号点")
        except api.LicenseError:
            print("未激活, 请先在主程序购买授权激活。"); break
        except Exception as e:
            print("跳过", f, "原因:", e)

    if all_depth:
        pd.concat(all_depth, ignore_index=True).to_csv("all_water_depth.csv", index=False)
        print("已汇总所有水深 -> all_water_depth.csv")

### 示例 C — 命令行直接批处理
    python api.py D:\\icesat2\\data\\*.h5 --beams gt1l gt2r --outdir out --no-plots

## 4. 返回与输出
每个文件×波束的输出目录内含:
  photons_classified.csv  underwater_sdaf.csv  signal_refraction.csv
  bottom_terrain_line.csv  water_depth.csv  以及(若 make_plots)各步骤 PNG。
批处理根目录另有 batch_summary.csv 汇总每个组合的统计与状态。

## 5. 常见问题
- LicenseError: 本机未激活。请先用主程序"购买授权"完成离线激活。
- 某文件报"水下光子过少": 该波束/裁剪范围内有效水下信号不足, 换波束或调裁剪。
- 想更快: make_plots=False; 只跑需要的波束; 合理裁剪范围。

— 微信公众号: 遥感小屋
"""

EXAMPLE_SCRIPT = r'''# -*- coding: utf-8 -*-
"""
batch_example.py -- ICESat-2 浅海测深工具 批处理接口 调用示例
=====================================================================
需先在本机用主程序"购买授权"完成激活。把本脚本与 api.py 等放在同一目录,
改好下面的 FOLDER / BEAMS / OUTDIR 后运行: python batch_example.py
"""
import os
import pandas as pd
import api

# ====== 改这里 ======
FOLDER = r"D:\icesat2\data"        # 存放 .h5/.csv 的文件夹
BEAMS = ["gt1l", "gt2r"]            # 要处理的波束(可多条)
OUTDIR = r"D:\icesat2\out"         # 输出根目录
RECURSIVE = False                  # 是否递归子文件夹
MAKE_PLOTS = False                 # 批量时一般关掉出图更快
CROP = None                        # 例: {"mode":"bbox","lon_min":-64.9,"lon_max":-64.7,
                                   #       "lat_min":17.7,"lat_max":17.8}
PARAMS = None                      # 例: {"A_K_SIGMA":3.0, "C_N2":1.34}
# ====================


def main():
    if not api.licensing.is_activated():
        print("未激活: 请先用主程序‘购买授权’完成激活后再运行批处理。")
        return

    # 方式一: 一行批处理整个文件夹
    rows = api.batch_folder(FOLDER, beams=BEAMS, outdir=OUTDIR,
                            recursive=RECURSIVE, crop=CROP, params=PARAMS,
                            make_plots=MAKE_PLOTS, verbose=True)

    ok = [r for r in rows if r.get("status") == "ok"]
    bad = [r for r in rows if r.get("status") != "ok"]
    print(f"\n完成: 成功 {len(ok)} 个, 失败 {len(bad)} 个。明细见 {OUTDIR}\\batch_summary.csv")

    # 方式二(可选): 汇总所有水深到一张表(你自己的后处理)
    merged = []
    for r in ok:
        wd = os.path.join(r["outdir"], "water_depth.csv")
        if os.path.exists(wd):
            df = pd.read_csv(wd)
            df["source"] = os.path.basename(r["input"])
            df["beam"] = r["beam"]
            merged.append(df)
    if merged:
        out_csv = os.path.join(OUTDIR, "all_water_depth.csv")
        pd.concat(merged, ignore_index=True).to_csv(out_csv, index=False)
        print("已汇总全部水深 ->", out_csv)


if __name__ == "__main__":
    main()
'''


def save_usage_doc(path):
    """把接口说明导出为文档(.md/.txt)。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(USAGE_DOC)
    return path


def save_example_script(path):
    """生成一个可直接运行的批处理示例脚本。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(EXAMPLE_SCRIPT)
    return path


# ==========================================================================
# 面向"只发 exe(不给源码)"的命令行批处理 —— 用户无需 Python / 无需代码
# 同一个 exe: 双击=图形界面; 带参数=无界面批处理整个文件夹。
# ==========================================================================
def default_batch_config():
    """批处理配置模板(给最终用户编辑的 JSON)。"""
    return {
        "folder": "请改成你的数据文件夹, 例如 D:\\\\icesat2\\\\data",
        "beams": ["gt1l", "gt2r"],
        "outdir": "请改成输出文件夹, 例如 D:\\\\icesat2\\\\out",
        "recursive": False,
        "make_plots": False,
        "crop": {"mode": "none"},
        "params": {},
        "_说明": "folder=待处理文件夹; beams=波束(可多条); outdir=输出目录; "
                 "recursive=是否含子文件夹; make_plots=是否出图(批量建议false更快); "
                 "crop 不裁剪用 {\"mode\":\"none\"}; params 留空用默认参数。",
    }


def save_batch_config(path):
    """写出一份批处理配置模板 JSON, 供用户编辑后用 --batch-config 调用。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(default_batch_config(), f, ensure_ascii=False, indent=2)
    return path


def run_config(config):
    """按配置(JSON 路径或 dict)批处理。需先激活。"""
    if isinstance(config, dict):
        cfg = config
    else:
        with open(config, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    _require_license()
    folder = cfg.get("folder")
    if not folder or not os.path.isdir(folder):
        raise NotADirectoryError(f"配置里的 folder 无效: {folder}")
    crop = cfg.get("crop") or None
    if isinstance(crop, dict) and crop.get("mode", "none") == "none":
        crop = None
    return batch_folder(
        folder, beams=cfg.get("beams"), outdir=cfg.get("outdir", "batch_results"),
        recursive=bool(cfg.get("recursive", False)), crop=crop,
        params=(cfg.get("params") or None),
        make_plots=bool(cfg.get("make_plots", False)), verbose=True)


def _ensure_console():
    """Windows 上若是无控制台的窗口程序(-w 打包), 批处理时临时分配一个控制台显示进度。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        if k.GetConsoleWindow() == 0:
            k.AllocConsole()
            import sys as _sys
            _sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            _sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            try:
                _sys.stdin = open("CONIN$", "r")
            except Exception:
                pass
    except Exception:
        pass


CLI_HELP = """ICESat-2 浅海测深工具 — 命令行批处理(需先在本机激活永久授权)

用法(把 ICESat2Bathy.exe 换成你的软件文件名):
  1) 批处理一个文件夹:
       ICESat2Bathy.exe --batch "D:\\data" --beams gt1l gt2r --out "D:\\out"
       可选: --recursive(含子文件夹)  --no-plots(不出图更快)
  2) 用配置文件批处理(适合非技术用户, 改 JSON 即可):
       ICESat2Bathy.exe --batch-config "D:\\batch_config.json"
  3) 查看本帮助:
       ICESat2Bathy.exe --batch-help

说明:
  · 无需安装 Python、无需任何源码, 直接用软件本身即可批处理。
  · 未激活时会提示需先激活(打开软件 → 购买授权 完成离线激活)。
  · 每个文件×波束在输出目录下各有一个子文件夹, 含 water_depth.csv 等;
    输出根目录有 batch_summary.csv 汇总成败与统计。
"""


def cli_main(argv=None):
    """命令行批处理入口。返回进程退出码(0 成功 / 1 出错 / 2 未激活)。"""
    import argparse
    import sys as _sys
    if argv is None:
        argv = _sys.argv[1:]
    if "--batch-help" in argv:
        _ensure_console()
        print(CLI_HELP)
        return 0
    ap = argparse.ArgumentParser(prog="ICESat2Bathy", add_help=False)
    ap.add_argument("--batch", metavar="FOLDER", default=None)
    ap.add_argument("--batch-config", dest="batch_config", metavar="JSON", default=None)
    ap.add_argument("--beams", nargs="+", default=None)
    ap.add_argument("--out", "--outdir", dest="outdir", default="batch_results")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--no-plots", action="store_true")
    args, _unknown = ap.parse_known_args(argv)

    _ensure_console()
    if not licensing.is_activated():
        print("【未激活】批处理接口需要先激活永久授权。\n"
              "请双击打开软件 → 点‘购买授权’ → 完成离线激活后再运行批处理。")
        return 2
    try:
        if args.batch_config:
            rows = run_config(args.batch_config)
        elif args.batch:
            rows = batch_folder(args.batch, beams=args.beams, outdir=args.outdir,
                                recursive=args.recursive,
                                make_plots=not args.no_plots, verbose=True)
        else:
            print(CLI_HELP)
            return 1
    except Exception as e:
        print("批处理出错:", e)
        return 1
    ok = sum(1 for r in rows if r.get("status") == "ok")
    bad = len(rows) - ok
    print(f"\n完成: 成功 {ok} 个, 失败 {bad} 个。明细见输出目录的 batch_summary.csv")
    return 0


# ==========================================================================
# 面向 GUI‘数据批处理’窗口的运行器(单输出目录 + 原名_条带_阶段 命名 + 进度回调)
# ==========================================================================
def run_gui_batch(pairs, outdir, crop=None, params=None, make_plots=True,
                  save_all_csv=True, progress_cb=None, stop_flag=None,
                  log_cb=None):
    """对 (文件, 波束) 组合列表逐个跑全流程, 所有结果写入同一个 outdir,
    文件名为 ‘原数据名_波束_阶段’。需先激活。

    pairs       : [(input_path, beam), ...]
    progress_cb : callable(done:int, total:int, label:str) -> None  (线程安全由调用方保证)
    stop_flag   : callable() -> bool, 返回 True 则尽快中止
    log_cb      : callable(str) -> None, 输出每条日志
    返回: 每个组合的统计 dict 列表(含 status / error)。
    """
    _require_license()
    os.makedirs(outdir, exist_ok=True)
    total = len(pairs)
    results = []
    for i, (ip, bm) in enumerate(pairs):
        if stop_flag and stop_flag():
            if log_cb:
                log_cb("[批处理] 已被用户中止。\n")
            break
        stem = os.path.splitext(os.path.basename(ip))[0]
        label = f"{stem}  [{bm}]"
        if progress_cb:
            progress_cb(i, total, "正在处理: " + label)
        if log_cb:
            log_cb(f"[{i + 1}/{total}] 处理 {label} ...\n")
        try:
            res = process(ip, beam=bm, outdir=outdir, crop=crop, params=params,
                          make_plots=make_plots, verbose=False,
                          file_prefix=f"{stem}_{bm}_", save_all_csv=save_all_csv)
            s = res["summary"]
            s["source"] = os.path.basename(ip)
            results.append(s)
            if log_cb:
                log_cb(f"    完成: 信号点 {s['n_signal']}, 地形节点 "
                       f"{s['n_terrain_nodes']}, 用时 {s['elapsed_s']} s\n")
        except Exception as e:
            results.append({"input": ip, "source": os.path.basename(ip), "beam": bm,
                            "outdir": os.path.abspath(outdir),
                            "status": "error", "error": str(e)})
            if log_cb:
                log_cb(f"    跳过(出错): {e}\n")
    if progress_cb:
        progress_cb(total, total, "批处理完成")
    try:
        pd.DataFrame(results).to_csv(os.path.join(outdir, "batch_summary.csv"),
                                     index=False, encoding="utf-8-sig")
    except Exception:
        pass
    return results


def merge_depth_points(outdir, out_path, fmt="csv"):
    """把 outdir 下所有 ‘*_water_depth.csv’ 合并成一个研究区测深点文件。
    fmt: 'csv' -> CSV; 'shp' -> ESRI Shapefile(需 geopandas, 缺失则回退 CSV)。
    返回 (实际写出路径, 合并点数)。"""
    import glob
    files = sorted(glob.glob(os.path.join(outdir, "*_water_depth.csv")))
    if not files:
        # 兼容子文件夹式输出
        files = sorted(glob.glob(os.path.join(outdir, "*", "water_depth.csv")))
    if not files:
        raise FileNotFoundError("未找到任何 *_water_depth.csv, 请先运行批处理。")
    frames = []
    for f in files:
        try:
            d = pd.read_csv(f)
        except Exception:
            continue
        base = os.path.basename(f).replace("_water_depth.csv", "")
        d["source_beam"] = base
        frames.append(d)
    if not frames:
        raise RuntimeError("读取测深点失败。")
    merged = pd.concat(frames, ignore_index=True)
    if "lon" in merged and "lat" in merged:
        merged = merged.dropna(subset=["lon", "lat"]).reset_index(drop=True)

    if fmt.lower() == "shp":
        try:
            import geopandas as gpd
            from shapely.geometry import Point
            geom = [Point(xy) for xy in zip(merged["lon"], merged["lat"])]
            gdf = gpd.GeoDataFrame(merged, geometry=geom, crs="EPSG:4326")
            if not out_path.lower().endswith(".shp"):
                out_path += ".shp"
            gdf.to_file(out_path, encoding="utf-8")
            return out_path, len(merged)
        except Exception as e:
            csv_path = os.path.splitext(out_path)[0] + ".csv"
            merged.to_csv(csv_path, index=False, encoding="utf-8-sig")
            raise RuntimeError(
                f"导出 SHP 失败({e}); 已改存为 CSV: {csv_path}")
    else:
        if not out_path.lower().endswith(".csv"):
            out_path += ".csv"
        merged.to_csv(out_path, index=False, encoding="utf-8-sig")
        return out_path, len(merged)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ICESat-2 浅海测深 批处理接口(需先激活)")
    ap.add_argument("inputs", nargs="+", help="一个或多个 .h5/.csv 文件, 或文件夹")
    ap.add_argument("--beams", nargs="+", default=["gt1l"], help="波束列表")
    ap.add_argument("--outdir", default="batch_results")
    ap.add_argument("--recursive", action="store_true", help="文件夹递归扫描子目录")
    ap.add_argument("--no-plots", action="store_true", help="不输出 PNG(更快)")
    args = ap.parse_args()
    # 允许传文件夹: 自动展开成其中的 .h5/.csv
    files = []
    for ip in args.inputs:
        if os.path.isdir(ip):
            files.extend(list_data_files(ip, recursive=args.recursive))
        else:
            files.append(ip)
    rows = batch(files, beams=args.beams, outdir=args.outdir,
                 make_plots=not args.no_plots, verbose=True)
    print("\n==== 批处理汇总 ====")
    for r in rows:
        print(r)
