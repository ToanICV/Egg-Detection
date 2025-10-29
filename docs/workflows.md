+ Khi khởi động, PC ở trạng thái `Nghỉ`. PC gửi sang Actor lệnh `Di chuyển tiến`. Actor phản hồi về PC lệnh `ACK` và PC sẽ đi vào trạng thái `Scan and move`
+ Trong trạng thái `Scan and move` PC vừa xử lý ảnh nhận dạng trứng vừa mỗi 1 giây gửi lệnh `Đọc trạng thái 1`. 
    + Khi `nhận dạng được trứng` và có `ít nhất 1 quả ở giữa khung hình` hoặc `khoảng cách tới vật cản nhỏ hơn 30 cm` thì PC gửi lệnh `Dừng` sang Actor, Actor phản hồi về PC lệnh `ACK` và PC chuyển sang trạng thái `Pick up egg`.
        + Trong trạng thái `Pick up egg`, nếu có nhiều trứng thì PC sẽ chọn 1 quả và PC gửi lệnh `Điều khiển nhặt` sang Arm. Arm sẽ phản hồi lệnh `ACK` sang PC. Sau đó, mỗi giây PC gửi lệnh `Đọc trạng thái 2` sang Arm để kiểm tra Arm nhặt xong chưa. Arm sẽ phản hồi lệnh `Phản hồi 2`. Nếu Arm nhặt xong thì PC gửi tiếp lệnh `Điều khiển nhặt` sang Arm để tiếp tục nhặt cho đến khi hết trứng trong khung hình. Khi hết trứng thì PC gửi sang Actor lệnh `Di chuyển tiến` và vào trạng thái `Scan and move`
    + Khi `không nhìn thấy trứng` và `khoảng cách tới vật cản nhỏ hơn 30 cm` thì PC gửi sang Actor lệnh `Xoay 90 độ`, Actor phản hồi về PC lệnh `ACK` và PC đi vào trạng thái `Turn 1st`.
+ Trong trạng thái `Turn 1st`, PC sẽ định kỳ mỗi giây gửi sang Actor lệnh `Đọc trạng thái 1`. Actor trả về `Trạng thái 1` là đang xoay hoặc đứng yên. Nếu đang xoay thì 1 giây tiếp theo lại gửi lệnh `Đọc trạng thái 1` tiếp còn nếu đứng yên thì PC chuyển sang trạng thái `Scan only`.
+ Trong trạng thái `Scan only`:
    + Nếu nhận dạng được trứng thì PC chuyển sang trạng thái `Pick up egg`. 
        + Khi ở trạng thái `Pick up egg`, nếu có nhiều trứng thì PC sẽ chọn 1 quả và PC gửi lệnh `Điều khiển nhặt` sang Arm. Arm sẽ phản hồi lệnh `ACK` sang PC. Sau đó, mỗi giây PC gửi lệnh `Đọc trạng thái 2` sang Arm để kiểm tra Arm nhặt xong chưa. Arm sẽ phản hồi lệnh `Phản hồi 2`. Nếu Arm nhặt xong thì PC gửi tiếp lệnh `Điều khiển nhặt` sang Arm để tiếp tục nhặt cho đến khi hết trứng trong khung hình. Khi hết trứng thì PC gửi sang Actor lệnh `Di chuyển tiến` và vào trạng thái `Scan and move`
    + Nếu sau 5 giây mà không nhận dạng được trứng thì PC gửi sang Actor lệnh `Di chuyển tiến`, Actor phản hồi về PC lệnh `ACK` và PC đi vào trạng thái `Move only`.
+ Trong trạng thái `Move only`, PC `đếm ngược trong 5s` và gửi lệnh `Xoay 90 độ` sang Actor. Actor phản hồi về PC lệnh `ACK` và PC đi vào trạng thái `Turn 2nd`. 
+ Trong trạng thái `Turn 2nd`, PC sẽ định kỳ mỗi giây gửi sang Actor lệnh `Đọc trạng thái 1`. Actor trả về `Trạng thái 1` là đang xoay hoặc đứng yên. Nếu đang xoay thì 1 giây tiếp theo lại gửi lệnh `Đọc trạng thái 1` tiếp còn nếu đứng yên thì PC chuyển sang trạng thái `Scan and move`.---

## Ghi ch� tri?n khai (2025-10)
- Thu m?c `src/serial_io` cung c?p `ActorLink` v� `ArmLink` cho giao th?c khung `{0x24 0x24 ... 0x23 0x23}`; `FrameCodec` t? x? l� CRC v� ph?c h?i khi d? d�i khai b�o sai.
- `src/services` ch?a `EventBus` v� `CommandScheduler`; c�c timer ch�nh: `actor_status` (1s), `arm_status` (1s), `scan_only_timeout` (5s), `move_only_countdown` (5s).
- `src/state_machine` tri?n khai `ControlStateMachine` (theo c�c tr?ng th�i t�i li?u), `ControlContext` qu?n l� queue nh?t tr?ng, timer v� t?a d? Arm, `ControlEngine` n?i serial + scheduler + event bus.
- `src/main.py` publish `DetectionEvent` m?i khung h�nh (d� l?c ROI) v� d? state machine di?u khi?n to�n b? Actor/Arm.
- Ki?m th?: `tests/test_serial_codec.py`, `tests/test_scheduler.py`, `tests/test_state_machine.py` (ch?y `pytest` sau khi c�i d?t `pip install pytest`).
- `config/app.yaml` cho ph�p d�ng chung 1 block `control.serial` (c� th? m? r?ng th�m `actor`/`arm` n?u c?n c?u h�nh ri�ng).
- `camera.device_index` c� th? tr? t?i webcam, stream IP ho?c du?ng d?n file ?nh/video; h? th?ng s? t? ch?n ngu?n ph� h?p.
