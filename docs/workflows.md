+ Khi khởi động, PC ở trạng thái `Idle`: PC -> trạng thái `Scan and move`.

+ Trong trạng thái `Scan and move`:
    + on_enter: 
        + Gửi lệnh `Di chuyển tiến`
        + Bắt đầu polling gửi lệnh `Đọc trạng thái 1`.
        + Đăng ký nhận sự kiện từ module nhận dạng trứng.
    + transition:
        + Khi `nhận dạng được trứng` và có `ít nhất 1 quả ở giữa khung hình (0.25-0.75)*H theo trục Y` hoặc `khoảng cách tới vật cản nhỏ hơn 30 cm` -> PC gửi lệnh `Dừng` sang Actor, Actor phản hồi về PC lệnh `ACK` và PC chuyển sang trạng thái `Pick up egg`.
        + Khi `không nhìn thấy trứng` và `khoảng cách tới vật cản nhỏ hơn 30 cm` thì PC gửi sang Actor lệnh `Xoay 90 độ`, Actor phản hồi về PC lệnh `ACK` và PC đi vào trạng thái `Turn 1st`.

+ Trong trạng thái `Pick up egg`:
    + transition:
        + Nếu có nhiều trứng thì PC sẽ chọn 1 quả và PC gửi lệnh `Điều khiển nhặt` sang Arm. Arm sẽ phản hồi lệnh `ACK` sang PC. Sau đó, mỗi giây PC gửi lệnh `Đọc trạng thái 2` sang Arm để kiểm tra Arm nhặt xong chưa. Arm sẽ phản hồi lệnh `Phản hồi 2`. 
            + Nếu Arm nhặt xong thì PC gửi tiếp lệnh `Điều khiển nhặt` sang Arm để tiếp tục nhặt cho đến khi hết trứng trong khung hình. 
            + Khi hết trứng thì PC gửi sang Actor lệnh `Di chuyển tiến` và vào trạng thái `Scan and move`
    
+ Trong trạng thái `Turn 1st`:
    + on_enter: polling mỗi giây gửi sang Actor lệnh `Đọc trạng thái 1`.
    + transition: 
        + Nếu đang xoay thì 1 giây tiếp theo lại gửi lệnh `Đọc trạng thái 1` tiếp;
        + Nếu đứng yên thì PC chuyển sang trạng thái `Scan only`.

+ Trong trạng thái `Scan only`:
    + on_enter: 
        + Bắt đầu bộ đếm ngược 5 giây;
        + Đăng ký nhận sự kiện từ module nhận dạng trứng.
    + transition: 
        + Nếu nhận dạng được trứng thì PC chuyển sang trạng thái `Pick up egg`. 
        + Nếu sau 5 giây mà không nhận dạng được trứng thì PC gửi sang Actor lệnh `Di chuyển tiến`, Actor phản hồi về PC lệnh `ACK` và PC đi vào trạng thái `Move only`.

+ Trong trạng thái `Move only`:
    + on_enter: 
        + PC `đếm ngược trong 5s` 
    + transition:
        + gửi lệnh `Xoay 90 độ` sang Actor. Actor phản hồi về PC lệnh `ACK` và PC đi vào trạng thái `Turn 2nd`. 

+ Trong trạng thái `Turn 2nd`:
    + on_enter:
        + Polling  lệnh `Đọc trạng thái 1`. Actor trả về `Trạng thái 1` là đang xoay hoặc đứng yên. 
    + transition:
        + Nếu đang xoay thì 1 giây tiếp theo lại gửi lệnh `Đọc trạng thái 1` tiếp;
        + Nếu đứng yên thì PC chuyển sang trạng thái `Scan and move`.
