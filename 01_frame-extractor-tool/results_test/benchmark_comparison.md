# Benchmark comparison (test split)

| run | mAP50 | mAP50_95 | precision | recall | fitness | epochs | best_epoch | final_val_box_loss | final_val_cls_loss | final_val_dfl_loss | train_time_min |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| noaug | 0.5585 | 0.3150 | 0.6960 | 0.5618 | 0.3150 | 50 | 10 | 1.4639 | 1.3862 | 1.4449 | 43.4548 |
| aug | 0.6146 | 0.3670 | 0.7724 | 0.5951 | 0.3670 | 50 | 50 | 1.2356 | 0.9003 | 1.1802 | 49.7298 |
