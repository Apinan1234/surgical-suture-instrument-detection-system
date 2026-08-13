# Hyperparameter summary per run

| hyperparameter | noaug | aug | aug150 | aug960 |
| --- | ---: | ---: | ---: | ---: |
| model | yolo11n.pt | yolo11n.pt | yolo11n.pt | D:\ml\runs\ssid9_aug_960\train\weights\last.pt |
| epochs | 50 | 50 | 150 | 150 |
| batch | 8 | 8 | 8 | 8 |
| imgsz | 640 | 640 | 640 | 960 |
| seed | 42 | 42 | 42 | 42 |
| device | 0 | 0 | 0 | 0 |
| workers | 0 | 0 | 0 | 0 |
| optimizer | auto | auto | auto | auto |
| lr0 | 0.0100 | 0.0100 | 0.0100 | 0.0100 |
| lrf | 0.0100 | 0.0100 | 0.0100 | 0.0100 |
| momentum | 0.9370 | 0.9370 | 0.9370 | 0.9370 |
| weight_decay | 0.0005 | 0.0005 | 0.0005 | 0.0005 |
| warmup_epochs | 3.0000 | 3.0000 | 3.0000 | 3.0000 |
| patience | 100 | 100 | 100 | 100 |
| close_mosaic | 0 | 10 | 10 | 10 |
| amp | True | True | True | True |
| deterministic | True | True | True | True |
| hsv_h | 0.0000 | 0.0150 | 0.0150 | 0.0150 |
| hsv_s | 0.0000 | 0.7000 | 0.7000 | 0.7000 |
| hsv_v | 0.0000 | 0.4000 | 0.4000 | 0.4000 |
| degrees | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| translate | 0.0000 | 0.1000 | 0.1000 | 0.1000 |
| scale | 0.0000 | 0.5000 | 0.5000 | 0.5000 |
| shear | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| perspective | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| flipud | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fliplr | 0.0000 | 0.5000 | 0.5000 | 0.5000 |
| bgr | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| mosaic | 0.0000 | 1.0000 | 1.0000 | 1.0000 |
| mixup | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| cutmix | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| copy_paste | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| ** DIFFERS ** | model, epochs, imgsz, close_mosaic, hsv_h, hsv_s, hsv_v, translate, scale, fliplr, mosaic | model, epochs, imgsz, close_mosaic, hsv_h, hsv_s, hsv_v, translate, scale, fliplr, mosaic | model, epochs, imgsz, close_mosaic, hsv_h, hsv_s, hsv_v, translate, scale, fliplr, mosaic | model, epochs, imgsz, close_mosaic, hsv_h, hsv_s, hsv_v, translate, scale, fliplr, mosaic |
