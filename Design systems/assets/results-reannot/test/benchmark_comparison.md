# Benchmark comparison (test split)

| run | mAP50 | mAP50_95 | precision | recall | fitness | epochs | best_epoch | final_val_box_loss | final_val_cls_loss | final_val_dfl_loss | train_time_min |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| aug960 | 0.7015 | 0.4348 | 0.7331 | 0.6926 | 0.4348 | 150 | 139 | 1.2239 | 0.8829 | 1.2882 | 97.8928 |
| baseline9-reannot | 0.7212 | 0.4352 | 0.7158 | 0.7645 | 0.4352 | 150 | 100 | 1.2767 | 0.9169 | 1.3294 | 329.3983 |
