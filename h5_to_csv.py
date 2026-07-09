# -*- coding: utf-8 -*-
"""
Step 0 -- ATL03 (.h5) -> CSV converter
=====================================================================
论文复现配套代码:把 ICESat-2 ATL03 全球地理定位光子产品(HDF5)
中某一条 ground track(波束) 的光子点云抽取成后续步骤可以直接读取的 CSV。

输出列(后续 A/B/C 步骤都基于这些列):
    lat        : 光子纬度 (deg, WGS84)
    lon        : 光子经度 (deg, WGS84)
    h          : 光子椭球高 h_ph (m, WGS84)             -> 论文中 elevation(纵轴)
    x_atc      : 沿轨距离 (m)  = segment_dist_x + dist_ph_along  -> 论文中 distance along track(横轴)
    delta_time : 光子时间 (s)
    conf_ocean : 海洋面信号置信度 (signal_conf_ph 的 ocean 通道, -2..4)
    ref_elev   : 参考光子高度角 (rad), 折射改正用 (θ1 = π/2 - ref_elev)

ATL03 内部结构(NASA ATBD):
    /gt1l|gt1r|gt2l|gt2r|gt3l|gt3r/
        heights/    : lat_ph, lon_ph, h_ph, dist_ph_along, delta_time, signal_conf_ph
        geolocation/: ref_elev, segment_dist_x, segment_ph_cnt, segment_id
geolocation 数组是“按 20m 分段”存的, 需要按 segment_ph_cnt 展开到每个光子。

用法:
    python h5_to_csv.py  ATL03_xxx.h5  --beam gt2r  --out st_croix_2r.csv
    python h5_to_csv.py  ATL03_xxx.h5  --beam gt2r  --lat-min 17.75 --lat-max 17.81
"""
import argparse
import os
import numpy as np
import pandas as pd

try:
    import h5py
except ImportError:  # pragma: no cover
    h5py = None


# signal_conf_ph 的列含义: [land, ocean, sea_ice, land_ice, inland_water]
OCEAN_COL = 1


# ====================================================================
# 数据裁剪: 按经纬度边框 或 shp 多边形裁剪(只筛选行, 所有列/结构不变)
# ====================================================================
def crop_by_bbox(df, lon_min=None, lon_max=None, lat_min=None, lat_max=None):
    """按经纬度边框裁剪(四个角)。任一为 None 则该侧不限。返回筛选后的 DataFrame。"""
    m = np.ones(len(df), dtype=bool)
    if lon_min is not None:
        m &= df["lon"].to_numpy() >= float(lon_min)
    if lon_max is not None:
        m &= df["lon"].to_numpy() <= float(lon_max)
    if lat_min is not None:
        m &= df["lat"].to_numpy() >= float(lat_min)
    if lat_max is not None:
        m &= df["lat"].to_numpy() <= float(lat_max)
    return df[m].reset_index(drop=True)


def _points_in_ring(lon, lat, ring):
    """纯 numpy 射线法: 判断点是否在单个多边形环内(向量化, 无需 shapely)。"""
    lon = np.asarray(lon, float); lat = np.asarray(lat, float)
    px = np.asarray([p[0] for p in ring], float)
    py = np.asarray([p[1] for p in ring], float)
    n = len(px)
    inside = np.zeros(len(lon), bool)
    if n < 3:
        return inside
    j = n - 1
    for i in range(n):
        cond = (py[i] > lat) != (py[j] > lat)
        denom = (py[j] - py[i])
        denom = np.where(denom == 0, 1e-300, denom)
        xint = (px[j] - px[i]) * (lat - py[i]) / denom + px[i]
        inside ^= cond & (lon < xint)
        j = i
    return inside


def read_shapefile_polygons(shp_path):
    """读取 shp 中所有多边形的外环坐标列表 [[(lon,lat),...], ...]。
    优先 geopandas(可自动按 .prj 转 WGS84), 退而用 pyshp(shapefile), 都没有则报错。
    注意: 若 shp 不是经纬度(WGS84)坐标, 用 pyshp 时不做投影变换, 请先转为 EPSG:4326。"""
    # 1) geopandas: 最稳, 会处理坐标系
    try:
        import geopandas as gpd
        gdf = gpd.read_file(shp_path)
        try:
            if gdf.crs is not None:
                gdf = gdf.to_crs(epsg=4326)
        except Exception:
            pass
        rings = []
        for geom in gdf.geometry:
            if geom is None:
                continue
            gt = geom.geom_type
            if gt == "Polygon":
                rings.append(list(geom.exterior.coords))
            elif gt == "MultiPolygon":
                for g in geom.geoms:
                    rings.append(list(g.exterior.coords))
        if rings:
            return rings
    except Exception:
        pass
    # 2) pyshp(纯 python, 易打包)
    try:
        import shapefile  # pyshp
        sf = shapefile.Reader(shp_path)
        rings = []
        for shp in sf.shapes():
            pts = shp.points
            parts = list(shp.parts) + [len(pts)]
            for i in range(len(parts) - 1):
                ring = pts[parts[i]:parts[i + 1]]
                if len(ring) >= 3:
                    rings.append([(p[0], p[1]) for p in ring])
        if rings:
            return rings
        raise ValueError("shp 中未找到多边形")
    except ImportError:
        raise ImportError(
            "读取 shp 需要 geopandas 或 pyshp。请安装其一: \n"
            "    pip install pyshp        (轻量, 推荐随软件打包)\n"
            "    pip install geopandas    (功能全, 可自动转坐标系)")


def crop_by_shapefile(df, shp_path):
    """用 shp 多边形(可多个/多部件)裁剪点: 落在任一多边形内即保留。"""
    rings = read_shapefile_polygons(shp_path)
    lon = df["lon"].to_numpy(); lat = df["lat"].to_numpy()
    keep = np.zeros(len(df), bool)
    for ring in rings:
        keep |= _points_in_ring(lon, lat, ring)
    return df[keep].reset_index(drop=True)


def apply_crop(df, spec):
    """按裁剪规格统一裁剪。spec 为 dict:
        {"mode": "none"}                                          -> 不裁剪
        {"mode": "bbox", "lon_min","lon_max","lat_min","lat_max"} -> 经纬度边框
        {"mode": "shp", "path": "xxx.shp"}                        -> shp 多边形
    只筛选行, 所有列与数据结构保持不变。"""
    if not spec or spec.get("mode", "none") == "none":
        return df.reset_index(drop=True)
    if spec["mode"] == "bbox":
        return crop_by_bbox(df, spec.get("lon_min"), spec.get("lon_max"),
                            spec.get("lat_min"), spec.get("lat_max"))
    if spec["mode"] == "shp":
        return crop_by_shapefile(df, spec["path"])
    return df.reset_index(drop=True)


def crop_spec_tag(spec):
    """把裁剪规格转成稳定短字符串, 用于授权计数的“数据身份”。"""
    if not spec or spec.get("mode", "none") == "none":
        return "crop=none"
    if spec["mode"] == "bbox":
        return ("crop=bbox;{lon_min}~{lon_max};{lat_min}~{lat_max}"
                .format(**{k: spec.get(k) for k in
                           ("lon_min", "lon_max", "lat_min", "lat_max")}))
    if spec["mode"] == "shp":
        return "crop=shp;" + os.path.basename(str(spec.get("path", "")))
    return "crop=?"


def _expand_per_segment(values_per_seg, ph_cnt_per_seg):
    """把按分段存储的量(如 ref_elev, segment_dist_x)展开到每个光子。"""
    return np.repeat(values_per_seg, ph_cnt_per_seg)


def read_atl03_beam(h5_path, beam="gt2r", progress_cb=None, chunk=2_000_000):
    """读取单波束光子, 返回 DataFrame。
    progress_cb(loaded, total): 可选回调, 分块读取时上报已加载光子数(供 GUI 进度显示)。"""
    if h5py is None:
        raise ImportError(
            "需要 h5py 读取 ATL03。请在你的环境中执行: pip install h5py")

    with h5py.File(h5_path, "r") as f:
        if beam not in f:
            avail = [k for k in f.keys() if k.startswith("gt")]
            raise KeyError(f"波束 {beam} 不存在。可用波束: {avail}")

        h = f[beam]["heights"]
        g = f[beam]["geolocation"]
        N = int(h["h_ph"].shape[0])

        lat = np.empty(N); lon = np.empty(N); h_ph = np.empty(N)
        dt = np.empty(N); dist_along = np.empty(N); conf_ocean = np.empty(N)
        conf_ds = h["signal_conf_ph"]; two_d = (conf_ds.ndim == 2)

        # 分块读取(降低峰值内存 + 可上报进度)
        for i in range(0, N, chunk):
            j = min(i + chunk, N); sl = slice(i, j)
            lat[sl] = h["lat_ph"][sl]
            lon[sl] = h["lon_ph"][sl]
            h_ph[sl] = h["h_ph"][sl]
            dt[sl] = h["delta_time"][sl]
            dist_along[sl] = h["dist_ph_along"][sl]
            c = conf_ds[sl]
            conf_ocean[sl] = c[:, OCEAN_COL] if two_d else c
            if progress_cb:
                progress_cb(j, N)

        ph_cnt = g["segment_ph_cnt"][:]               # 每段光子数
        seg_dist_x = g["segment_dist_x"][:]           # 每段沿轨起始距离
        ref_elev_seg = g["ref_elev"][:]               # 每段参考高度角

    # 段级量 -> 光子级量
    cum = np.cumsum(ph_cnt)
    if len(cum) and cum[-1] != N:
        keep = cum <= N
        ph_cnt = ph_cnt[keep]; seg_dist_x = seg_dist_x[keep]; ref_elev_seg = ref_elev_seg[keep]
    seg_dist_per_ph = _expand_per_segment(seg_dist_x, ph_cnt)
    ref_elev_per_ph = _expand_per_segment(ref_elev_seg, ph_cnt)

    m = min(len(seg_dist_per_ph), N)
    x_atc = seg_dist_per_ph[:m] + dist_along[:m]

    df = pd.DataFrame({
        "lat": lat[:m], "lon": lon[:m], "h": h_ph[:m], "x_atc": x_atc,
        "delta_time": dt[:m], "conf_ocean": conf_ocean[:m],
        "ref_elev": ref_elev_per_ph[:m],
    })
    if progress_cb:
        progress_cb(N, N)
    return df


def main():
    ap = argparse.ArgumentParser(description="ATL03 h5 -> csv")
    ap.add_argument("h5", help="ATL03 .h5 文件路径")
    ap.add_argument("--beam", default="gt2r",
                    help="波束: gt1l/gt1r/gt2l/gt2r/gt3l/gt3r (默认 gt2r)")
    ap.add_argument("--out", default=None, help="输出 csv 路径")
    ap.add_argument("--lat-min", type=float, default=None, help="纬度下限裁剪(聚焦海岸带)")
    ap.add_argument("--lat-max", type=float, default=None, help="纬度上限裁剪")
    args = ap.parse_args()

    df = read_atl03_beam(args.h5, args.beam)

    if args.lat_min is not None:
        df = df[df["lat"] >= args.lat_min]
    if args.lat_max is not None:
        df = df[df["lat"] <= args.lat_max]
    df = df.reset_index(drop=True)

    out = args.out or f"atl03_{args.beam}.csv"
    df.to_csv(out, index=False)
    print(f"[h5_to_csv] 波束 {args.beam}: 写出 {len(df)} 个光子 -> {out}")
    print(df.head())


if __name__ == "__main__":
    main()
