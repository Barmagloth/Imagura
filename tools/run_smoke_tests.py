from __future__ import annotations

import argparse
import os
import time

from run_unittest_target import run_parent


SMOKE_TARGETS = [
    "tests.test_smoke.ViewMathSmokeTests",
    "tests.test_smoke.ViewerSmokeTests",
    "tests.test_smoke.ImageSortingSmokeTests",
    "tests.test_smoke.LoaderSmokeTests",
    "tests.test_smoke.CurrentAndNeighborLoaderSmokeTests",
    "tests.test_smoke.LargeTextureCacheSmokeTests",
    "tests.test_smoke.AnimatedContentCacheSmokeTests",
    "tests.test_smoke.ExifMetadataCacheSmokeTests",
    "tests.test_smoke.ThumbnailSmokeTests",
    "tests.test_smoke.GalleryBehaviorSmokeTests",
    "tests.test_smoke.UIControlsSmokeTests",
    "tests.test_smoke.AnimatedPlaybackSmokeTests",
    "tests.test_smoke.TransformSmokeTests",
    "tests.test_smoke.FileDeletionSmokeTests",
    "tests.test_smoke.FileDialogSmokeTests",
    "tests.test_smoke.ConfigSmokeTests",
    "tests.test_smoke.UserSettingsSmokeTests",
    "tests.test_smoke.WindowFlagSmokeTests",
    "tests.test_smoke.ScaleOverlaySmokeTests",
    "tests.test_smoke.ZoomAnimationSmokeTests",
    "tests.test_smoke.ManualZoomSmokeTests",
    "tests.test_smoke.TextureTypeSmokeTests",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Imagura smoke tests with per-target timeouts.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout per unittest target.")
    parser.add_argument("--codex-run-id", default=f"codex-smoke-{os.getpid()}-{time.time_ns()}")
    args = parser.parse_args()

    os.environ["IMAGURA_CODEX_RUN"] = "1"
    os.environ["IMAGURA_CODEX_RUN_ID"] = args.codex_run_id

    for target in SMOKE_TARGETS:
        run_id = f"{args.codex_run_id}-{target.rsplit('.', 1)[-1]}"
        code = run_parent(target, args.timeout, run_id)
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
