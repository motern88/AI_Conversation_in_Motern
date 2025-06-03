# 构建台球领域通用数据集

我们决定依赖小铁台球门店大量运营数据，构建构建台球的领域通用数据集（Domain-General Datasets）。

该DGD由一个数据源和多个子数据集标注组成。由一个统一标准采集的视频数据源，和在该数据源基础上构建的能够支撑不同方向的子数据集标注信息（检测，分割，追踪，视频理解，三维重建等）

DGD结构如下：

```
Domain-General Datasets
├──data_source
├──annotation
|   ├──detection
|   ├──video_segmentation
|   ├──tracking
|   ├──video_understanding
...
|   └──4d_reconstruction
```



## 1. 数据源

由于多个子任务数据集均依赖相同的数据源，因此数据源必须尽可能完整齐全，而不能过早地切分成小块。同时数据源也需要完成信息的记录与绑定，例如，需要记录哪些视频是不同摄像头在同一时刻拍到关于同一张台的信息

data_source数据源中有多个样本：

```
data_source
├──data_[ID]_[START TIME]_[DURATION]
├──data_[ID]_[START TIME]_[DURATION]
...
└──data_[ID]_[START TIME]_[DURATION]
```

每个样本文件夹命名方式`data_[ID]_[START TIME]_[DURATION]`

其中：

- ID 样本编号：

  由六位数字组成，从000001、000002、...以此类推，每个样本拥有唯一ID

- START TIME 样本记录的起始时刻：

  样本记录的起始时刻的时间戳，使用格式 `YYYYMMDDThhmmss`；

  示例： `20240530T142530` 表示录制起始时间为2024年5月30号 14点25分30秒

  其中 `T` 分隔日期与时间

- DURATION 样本记录的持续时间：

  样本记录的持续时间，使用格式 `hhmmss`；

  示例：`061820` 表示持续6小时18分20秒

样本文件夹命名示例：`data_000136_20250603T103120_021015`

------

每个样本文件夹结构如下：

```
data_[ID]_[START TIME]_[DURATION]
├──[CAMERA TYPE]_[CAMERA ID]_[TABLE ID]_[START TIME]_[DURATION].mp4
├──[CAMERA TYPE]_[CAMERA ID]_[TABLE ID]_[START TIME]_[DURATION].mp4
├──[CAMERA TYPE]_[CAMERA ID]_[TABLE ID]_[START TIME]_[DURATION].mp4
...
└──info.json
```

每一个样本文件夹包含一段时间内场景中多个摄像头感知到的不同画面，包含多个MP4文件。每个MP4文件来自一个摄像头，其中：

- CAMERA TYPE 相机视角类型：

  正上方视角则为 overhead

  精彩秀视角则为 highlight

  监控视角则为 surveilance

- CAMERA ID 相机编号

  该门店内相机的编号，如果已有同一命名标准则沿用同一命名标准，如果没有，则重新分配唯一四位数编号。如0001、0002等。同一门店内，即同一data样本文件夹下，所有相机的ID均是唯一的

- TABLE ID 桌台编号

  如果是正上方摄像头和精彩秀摄像头则应该有对应的桌台编号，例如 A01、A02 等。如果是监控视角，则没有对应桌台，桌台编号则填写 000 。

- START TIME 该摄像头记录的起始时刻：

  样本记录的起始时刻的时间戳，使用格式 `YYYYMMDDThhmmss`；

  示例： `20240530T142530` 表示录制起始时间为2024年5月30号 14点25分30秒

  其中 `T` 分隔日期与时间

- DURATION 该摄像头记录的持续时间：

  样本记录的持续时间，使用格式 `hhmmss`；

  示例：`061820` 表示持续6小时18分20秒

摄像头视频命名示例：
`overhead_0012_B03_20240530T142530_061820.mp4`



每一个样本文件夹同时包含了一个json说明文件 `info.json` ，其中包含了对该样本场景及其中每个摄像头的说明：

```json
{
    "data_id": "000121",
    "data_start_time": "20240530T142530",
    "data_duration": "061820",
	"data_location": "XXXXXXXXX", 
	"videos":{
    	"overhead_0012_B03_20240530T142530_061820.mp4": {
            "camera_type": "overhead",
            "camera_id": "0012",
            "table_id": "B03",
            "start_time": "20240530T142530",
            "duration": "061820",
            "width": 1920,
            "height": 1080,
            "fps": 60,
        },
        "surveillance_0005_000_20240530T142530_061820.mp4": {
            "camera_type": "surveillance",
            "camera_id": "0005",
            "table_id": "000",
            "start_time": "20240530T142530",
            "duration": "061820",
            "width": 1920,
            "height": 1080,
            "fps": 24,
        },
        ...
	}
}
```

其中：

- data_id 样本ID:

  由六位数字组成，从000001、000002、...以此类推，每个样本拥有唯一ID

- data_start_time 样本记录起始时间:

  样本记录的起始时刻的时间戳，使用格式 `YYYYMMDDThhmmss`；
  示例： `20240530T142530` 表示录制起始时间为2024年5月30号 14点25分30秒
  其中 `T` 分隔日期与时间

- data_duration 样本记录持续时间：

  样本记录的持续时间，使用格式 `hhmmss`；
  示例：`061820` 表示持续6小时18分20秒

- data_location 样本记录来源的地址：

  填写门店地址字符串，以后台标准格式为准

- videos 视频内容：

  videos以字典形式记录多条视频内容，这些不同视角，不同桌台的视频共同组成了这段时间内的整个场景数据。字典中每个字段名为视频名称，对应的值为相应的该视频参数。

  以视频完整文件名称“`[CAMERA TYPE]_[CAMERA ID]_[TABLE ID]_[START TIME]_[DURATION].mp4`”的值包含以下字段：

  - camera_type 摄像机类型

    正上方视角则为 overhead；精彩秀视角则为 highlight；监控视角则为 surveilance

  - camera_id

    该门店内相机的编号，如果已有同一命名标准则沿用同一命名标准，如果没有，则重新分配唯一四位数编号。如0001、0002等。同一门店内，即同一data样本文件夹下，所有相机的ID均是唯一的

  - table_id

    如果是正上方摄像头和精彩秀摄像头则应该有对应的桌台编号，例如 A01、A02 等；如果是监控视角，则没有对应桌台，桌台编号则填写 000 

  - start_time 该视频起始时间：

    使用格式 `YYYYMMDDThhmmss`，示例 `20240530T142530` 表示录制起始时间为2024年5月30号14点25分30秒；其中 `T` 分隔日期与时间

  - duration 该视频持续时间：

    使用格式 `hhmmss`，示例 `061820` 表示持续6小时18分20秒

  - width 视频分辨率的宽：

    填int类型

  - height 视频分辨率的高：

    填int类型

  - fps 视频帧率：

    填int类型





**TODO：**需要确认

- data_location 门店地址后台标准格式
- camera_id 相机编号后台标准格式
- table_id 桌台后台标准格式
- 摄像头一些其他参数需要记录吗？要记录的话需要考虑数据收集时这些参数的获取难度





## 2. 子数据集标注

