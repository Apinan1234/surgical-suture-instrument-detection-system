# Benchmark comparison (val split)

| run | mAP50 | mAP50_95 | precision | recall | fitness | epochs | best_epoch | final_val_box_loss | final_val_cls_loss | final_val_dfl_loss | train_time_min |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| aug960 | 0.7160 | 0.4532 | 0.7335 | 0.7173 | 0.4532 | 150 | 139 | 1.2239 | 0.8829 | 1.2882 | 97.8928 |
| baseline9-reannot | 0.7225 | 0.4444 | 0.7359 | 0.7290 | 0.4444 | 150 | 100 | 1.2767 | 0.9169 | 1.3294 | 329.3983 |
