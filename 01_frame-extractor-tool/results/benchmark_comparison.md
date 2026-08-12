# Benchmark comparison (val split)

| run | mAP50 | mAP50_95 | precision | recall | fitness | epochs | best_epoch | final_val_box_loss | final_val_cls_loss | final_val_dfl_loss | train_time_min |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| noaug | 0.5746 | 0.3245 | 0.6985 | 0.5417 | 0.3245 | 50 | 10 | 1.4639 | 1.3862 | 1.4449 | 43.4548 |
| aug | 0.6559 | 0.4007 | 0.6872 | 0.6641 | 0.4007 | 50 | 50 | 1.2356 | 0.9003 | 1.1802 | 49.7298 |
