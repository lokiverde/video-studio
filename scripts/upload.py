"""Upload job outputs (or previews) to BunnyCDN storage and print public URLs."""
import argparse
import urllib.parse
import urllib.request

import common
import dash_rule


def put_file(cfg, local_path, remote_path):
    dash_rule.check_upload(local_path)          # Tony's dash rule: never upload a dashed file or folder
    key = cfg.get("BUNNY_STORAGE_KEY")
    base = cfg.get("BUNNY_STORAGE_BASE")
    if not key or not base:
        common.die("BUNNY_STORAGE_KEY / BUNNY_STORAGE_BASE not set in config.env")
    remote_path = urllib.parse.quote(remote_path)   # job folders can have spaces
    url = f"{base.rstrip('/')}/{remote_path}"
    req = urllib.request.Request(url, data=local_path.read_bytes(), method="PUT")
    req.add_header("AccessKey", key)
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=600) as resp:
        if resp.status not in (200, 201):
            raise RuntimeError(f"Bunny PUT {url} -> HTTP {resp.status}")
    return f"{cfg['BUNNY_PUBLIC_BASE'].rstrip('/')}/{remote_path}"


def run(job_id, previews=False):
    jdir = common.job_dir(job_id)
    dash_rule.check_folder(jdir)
    cfg = common.load_config()
    if previews:
        work = jdir / "work"
        files = (sorted(work.glob("scene_*.png")) + sorted(work.glob("p_scene_*.png"))
                 + [f for f in (work / "contact_sheet.jpg", work / "contact_sheet_9x16.jpg")
                    if f.exists()])
        files = [f for f in files if f.exists()]
        state_key = "preview_urls"
    else:
        files = [f for f in (jdir / "out" / "final_16x9.mp4", jdir / "out" / "final_9x16.mp4")
                 if f.exists()]
        if not files:
            common.die("no final renders found (run assemble first)")
        # Optional: only present when the thumbnail step succeeded.
        for extra in ("thumbnail.jpg", "transcript.txt", "transcript.srt", "youtube.md"):
            if (jdir / "out" / extra).exists():
                files.append(jdir / "out" / extra)
        state_key = "video_urls"
    files = dash_rule.keep_uploads(files)

    urls = []
    for f in files:
        url = put_file(cfg, f, f"faceless/{job_id}/{f.name}")
        urls.append(url)
        print(f"[upload] {url}")
    common.set_state(job_id, **{state_key: urls},
                     **({"status": "uploaded"} if not previews else {}))
    return urls


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--previews", action="store_true", help="upload stills + contact sheet instead of finals")
    a = p.parse_args()
    run(a.job, a.previews)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        common.die(str(err))
