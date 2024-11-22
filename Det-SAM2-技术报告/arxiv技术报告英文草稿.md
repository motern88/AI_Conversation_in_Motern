#### Det-SAM2: Technical Report on the Self-Prompting Segmentation Framework Based on Segment Anything Model 2

#### abstract

Segment Anything Model 2 (SAM2) demonstrates powerful video segmentation capabilities and the ability to refine segmentation results. We hope it can further evolve to achieve higher levels of automation for practical applications. We built on SAM2 with a series of attempts and ultimately developed a truly human-free pipeline (Det-SAM2), where object prompts are automatically provided by the detection model for SAM2 to perform inference and refinement. This pipeline allows for inference on infinitely long video streams with constant GPU and memory usage, while maintaining the same efficiency and accuracy as the original SAM2. 

This technical report focuses on the construction of the overall Det-SAM2 framework and the subsequent engineering optimization of SAM2. It also showcases an application example built using the Det-SAM2 framework: an AI referee for billiards scenarios. Project has been open-sourced at https://github.com/motern88/Det-SAM2.

#### 1. Introduction

Segment Anything Model 2 (SAM2)【1】 is currently the SOTA model in the field of video segmentation. It demonstrates advanced object-level instance segmentation capabilities and continues the mask fuzzy matching and interactive refinement features from Segment Anything (SAM)【2】. However, in the official implementation of SAM2, users must first interact with SAM2 on the initial frame of the video and apply condition prompts before inference can begin. During the inference process, if corrections are needed for SAM2's incorrect results, users must add new condition prompts near the erroneous frames and perform inference again. On one hand, frequent manual interactions limit the potential for SAM2 to be widely applied in automated scenarios. On the other hand, SAM2 requires re-inference from scratch each time new condition prompts and categories are added, which exacerbates the significant performance overhead already inherent in SAM2.

Therefore, we developed Det-SAM2. Det-SAM2 is a video object segmentation pipeline that automatically adds prompts to SAM2 using the YOLOv8【3】detection model, followed by post-processing of SAM2's segmentation results to make business judgments in specialized scenarios, all without human intervention. It retains SAM2's powerful object segmentation and refinement capabilities, while also solving the issue of requiring manual input of condition prompts, enabling automated inference. Moreover, we have implemented a series of engineering improvements to the Det-SAM2 framework, reducing performance overhead.

Specifically, our key contributions include:

1. We have implemented a self-prompting video instance segmentation pipeline (Det-SAM2-pipeline) that requires no manual interaction for prompt input. It supports inference and segmentation of specific categories (determined by a custom detection model) using **video streams**, and returns segmentation results with the same accuracy as SAM2 to support post-processing for business layer usage.

2. We have implemented the ability to **add new objects online during the SAM2 inference tracking process** without interrupting the inference state.
3. Our pipeline allows the application of a memory bank from one video to a new video, which we call a **preload memory bank**. It can leverage the memories (object categories, shapes, motion states) from the inference analysis of the previous video to assist in performing similar inference in the new video, **without the need to add any condition prompts in the new video**.

4. We have implemented **constant GPU and memory usage** in the Det-SAM2 pipeline, enabling the inference of infinitely long videos without interruption.

Our work is focused solely on engineering optimizations and does not involve training or fine-tuning the SAM2【1】 model itself. The tasks involved in the implementation of the Det-SAM2 framework and the development of its application example (AI referee for the billiards scene) are shown in 【**Figure 1**】.

![Det-SAM2整体规划](./asset/Det-SAM2整体规划.jpg)

【Figure 1】：Overview of Det-SAM2 Tasks. The overall technical pipeline consists of three components: the detection module, the pixel-level video tracking module using SAM2 instances, and the post-processing module. The detection model provides initial (potentially imperfect) bounding boxes, which are used as conditional prompts for SAM2. The SAM2 video predictor propagates these discrete frame prompts (propagate_in_video) across all frames in the video, performing continuous inference. Finally, the SAM2 video predictor outputs spatiotemporal masks for object instances throughout the video. The post-processing module analyzes the obtained masks to provide accurate and quantifiable results, supporting higher-level applications such as an AI coach or AI referee in billiards scenarios.

#### 2. Related Work

**Segment Anything Model 2**【1】achieves object segmentation in videos, leveraging its universal understanding of object-level concepts. It adeptly handles deformations such as stretching and occlusion, representing a groundbreaking advancement surpassing traditional detection and segmentation models. Additionally, SAM2 possesses robust correction capabilities, allowing newly provided conditional prompts to be applied across all previously inferred frames, enabling the correction of certain errors. The SAM2 Video Predictor, as illustrated in 【**Figure 2**】, stores the input image features and predicted mask results for each frame in the Memory Bank. During the prediction of the segmentation mask for each frame, the Memory Bank, conditional prompts, and input image features are all involved in the inference computation.

![SAM2框架图](./asset/SAM2框架图.jpg)

【Figure 2】：Original Framework of SAM2. The video frame features are processed through Memory Attention, integrating information from the current frame with that in the Memory Bank, and then passed to the Mask Decoder, which uses the conditional prompts to generate the predicted masks. The Memory Bank is extracted by the Memory Decoder from the conditional frames. The Memory Decoder receives outputs not only from the Mask Decoder but also from the Image Encoder.

**YOLOv8**【3】is a new version of the YOLO series launched by Ultralytics in 2023. It is built upon YOLOv5【4】, incorporating significant architectural and methodological innovations. Now, with excellent performance and wide applicability, YOLOv8 has become the preferred choice for industrial deployment in the field of object detection.

#### 3. Methodology

In this section, we focus on how we built the Det-SAM2 pipeline (corresponding to the seven subtasks in 【Figure 1】) and the series of engineering challenges addressed during this process.

#### 3.1 Detection Model + SAM2 Video Predictior

As mentioned earlier, interactive prompts are both the key to SAM2's【1】accurate segmentation and a barrier to achieving fully automated inference without human intervention. The initial prompt for SAM2's first input frame must be manually provided to start the inference process. We considered whether a detection model could replace the need for human-provided prompts.

As shown in 【**Figure 3**】, compared to 【**Figure 2**】, we added a branch connecting the video frames input to the prompt input. This branch is powered by a detection model, which applies prompts in the form of detection boxes to the video frames for our specified categories. With this branch, SAM2 can initiate predictions without human intervention. This marks the initial form of Det-SAM2 (Detection Model + SAM2 Video Predictor).

![Det-SAM2只在第一帧给提示框架图](./asset/Det-SAM2只在第一帧给提示框架图.jpg)

【Figure 3】：Det-SAM2 Experimental Demo Framework Diagram. The condition prompt for a given frame is automatically added, and the condition prompt is provided by the detection model (in this case, YOLOv8). The detection box results are used as the prompt input for the Prompt Encoder.

#### 3.2 Det-SAM2 in Video Stream

When our Det-SAM2 is able to start segmentation predictions without manual intervention, we also want it to inherit SAM2's powerful correction capability, rather than relying solely on the prompt information from the initial frame to infer the predictions for the entire video. We aim to continuously add Box prompts automatically generated by the detection model to SAM2 in the video stream. Due to SAM2's correction mechanism, whenever SAM2 receives a new prompt, it propagates the new prompt information to all previously inferred frames (using `propagate_in_video`). Thus, the memory bank, which now includes the newly received prompt, is reintroduced into the memory attention of each previously processed frame, and the segmentation masks for each frame are recalculated, thereby enabling corrections.

When we implement the automatic addition of condition prompts for each frame in the Det-SAM2 framework, the schematic diagram is shown in 【**Figure 4**】. The only difference between this and 【**Figure 3**】 is that we call the detection model branch for each frame. At the same time, the schematic diagram of Det-SAM2 in video stream along the time dimension (video stream direction) is shown in 【**Figure 5**】.

![Det-SAM2框架图](./asset/Det-SAM2框架图.jpg)

【Figure 4】：The Det-SAM2 framework allows for the automatic addition of condition prompts for each frame. Compared to 【**Figure 3**】, the detection model branch is not only active in the initial frame of the video, but is applied to every frame of the video.

<img src="./asset/视频流处理流程图.jpg" alt="视频流处理流程图" style="max-width:65%;" />

【Figure 5】：Det-SAM2 Video Stream Processing Diagram. Each frame passes through the Detection Model as a condition frame for SAM2 (represented in green in the diagram), and then the propagation operation (depicted in yellow as "propagate in video") is applied to all previously processed video frames to enable the correction capability.

However, as shown in 【**Figure 5**】, in practice, the propagation process (propagate_in_video) consumes a considerable amount of inference time. This is because, during the propagation, each time a new condition frame is added, SAM2 re-infers all previous frames. As a result, when processing a video of length $N$ frames, the current framework requires inference for a total of $$ \frac{1}{2} N^2 $$ frames.

#### 3.3 Cumulative Video Stream

A simple way to optimize inference overhead is to reduce the number of times the inference propagation (propagate_in_video) is performed. Reducing the number of propagation steps can be approached from two aspects: One approach is to reduce the frequency at which condition frames are generated, as only these frames trigger SAM2's correction mechanism, causing it to repeatedly perform inference propagation on previously processed frames. Another approach is to increase the number of video frames in a single input. When multiple frames are input at once, SAM2 will only propagate once.

Therefore, we aim to space out the inference of the detection model, so that not every frame input into SAM2 needs to have condition prompts added by the detection model. Moreover, our experiments have shown that if every frame is conditioned by the detection model, once a non-condition frame appears, it will fail to predict the segmentation mask due to SAM2's over-reliance on frequent condition prompts.

We also aim to allow new incoming video frames to accumulate in a video frame buffer while receiving the video stream. Instead of inputting each frame into the Det-SAM2 framework individually, we input a sequence of accumulated frames all at once. This way, SAM2 processes multiple frames in a single pass, reducing the number of propagation steps.

The diagram of the process for accumulating the video stream and spacing out the condition prompts from the detection model is shown in 【**Figure 6**】.

<img src="./asset/视频流累积处理+间隔检测流程图.jpg" alt="视频流累积处理+间隔检测流程图" style="max-width:80%;" />

【Figure 6】：Flowchart of cumulative video stream and interval-based detection condition prompts in Det-SAM2. For each frame received in the video stream, it will first be accumulated in the frame buffer. When the frame buffer accumulates enough frames, we will input the sequence of frames from the buffer into the Det-SAM2 framework all at once. During inference of the current video frame sequence, SAM2 will determine which frames are condition frames and which are non-condition frames based on the interval setting. Condition frames are provided with condition prompts by the detection model, and the prompt embeddings are generated by SAM2's Prompt Encoder.

By accumulating a certain number of video frames before inference, we can significantly reduce the number of propagation steps in SAM2. Suppose we accumulate a sequence of $K$ frames at a time. When performing inference on an entire video of length $N$ frames, the propagation process (`propagate_in_video`) would only need to process approximately $$ \frac{1}{2K} N^2 $$ frames.

#### 3.4 Limited Video Propagate

We already know that SAM2【1】achieves prompt-based corrections by receiving new conditional prompts and performing re-inference propagation (`propagate_in_video`) across all historical frames. In a static video (i.e., when the entire video is input at once), it is understandable that each propagation needs to be performed across all frames of the video. However, during inference on a video stream, it is not necessary for the propagation process to be executed on all historical frames.

In the actual Det-SAM2 process, the non-condition frames that require correction are usually not too far apart from the condition frames they depend on. Therefore, we can limit the number of frames involved in the inference during each propagation. During each inference process in the video stream, the majority of distant past frames are already finalized and do not require correction. In contrast, the more recent a past frame is, the more likely its inference results may be overturned in future predictions. Therefore, we need to impose the following restrictions on the propagation operation (`propagate_in_video`):

1. Set the propagate_in_video to process frames in reverse order, starting from the most recent frame.
2. Limit the maximum number of frames to be processed during propagation (`propagate_in_video`). However, the length of the propagation should at least fully cover the cumulative video frame sequence from the previous inference; otherwise, the propagation would lose its corrective significance.

The process diagram for Limited Video Propagation is illustrated in 【**Figure 7**】.

![限制最大传播长度](./asset/限制最大传播长度.jpg)

【Figure 7】：Flow Diagram of Limited Video Propagation: During propagation (propagate in video), the process is restricted to a user-defined maximum tracking length (max_frame_num_to_track), instead of iterating through all previous frames.

Increasing the maximum propagation length (max_frame_num_to_track) can expand the correction range but will result in higher computational overhead. Conversely, reducing the maximum propagation length can accelerate inference speed but will limit the range within which conditional frames can correct non-conditional frames in the video stream.

By limiting the propagation length (max_frame_num_to_track) to $$M$$, and the cumulative frame buffer size (frame_buffer_size) to $$K$$, inference for a video of length $$N$$ frames requires processing approximately $$ \frac{M}{K} N $$ frames. This implies that when $$M$$ and $$N$$ are fixed, the actual number of frames processed by Det-SAM2 increases linearly with the video length.

#### 3.5 Preload Memory Bank（Offline Memory Bank）

SAM2【1】 compared to SAM【2】, an important improvement that enables the transfer of image segmentation capabilities to video segmentation is the addition of the Memory Bank. This Memory Bank can establish associations between frames through Memory Attention, allowing SAM2 to leverage temporal context across video frames for improved segmentation performance. However, the generation and construction of the Memory Bank must be online, meaning it needs to be built in real-time during the inference process. Each time a new video frame is input, the Memory Bank is updated with the condition prompt, output mask, and video frame feature through the Memory Decoder.

nspired by discussions in the official code repository issues【5】, we aim to preload a Memory Bank that has already been constructed from an old video. This would allow us to utilize the memory information from the previous video on the new video, enabling inference without the need to add any condition prompts. This means allowing SAM2 to preload an offline Memory Bank, which has been carefully designed to include all the necessary prompts and difficult sample prompts that might be needed for the new video, similar to a "system prompt." During subsequent inference on the new video, the newly generated memory will be accumulated on top of the preloaded Memory Bank. The newly generated memory and the preloaded memory are conceptually distinguished, but during actual inference in SAM2, there is no distinction between the two. The process of preloading the memory bank is illustrated in 【**Figure 8**】.

![预加载内存库](./asset/预加载内存库.jpg)

【Figure 8】：Preload memory bank flowchart. The Memory Bank pre-loads an offline memory bank, sourced from previously inferred videos. As a result, during the current inference, the previously inferred memory from past videos can be directly applied to the inference of the new video.

In the specific implementation, the `inference_state` in SAM2 holds all the information in the memory bank. Therefore, by migrating the `inference_state` to the new video inference, the new video can directly leverage the existing memory without needing to reinitialize the `init_state`.

#### 3.6 Support Add New Objects in Tracking

As of now, in the official SAM2 implementation, it is only allowed to pre-define the instances that need to be segmented before the tracking begins, and it does not support the online addition of new instances to be segmented during the tracking process. The specific reason is that when the memory bank is first initialized (`init_state`), the class mapping list is fixed. If new object categories that need to be inferred are introduced in a new frame, it would cause a mismatch in the feature tensor sizes between the new frame and the old frames, making it impossible to compute.

In fact, during the real-time video stream processing with Det-SAM2, most of the time, we cannot predict what objects will appear in the future. Our detection model is likely to output only a partial set of categories when initializing the memory bank for the first time. The remaining categories, when introduced to SAM2 after the inference begins, would appear as new objects that need to be processed during the inference. This situation is unavoidable. The official solution to this is to perform a `reset_state`, which resets the memory bank. This means that in the frame where a new category appears, the memory bank is reinitialized. The consequence of this approach is that all previous inference results are lost, and segmentation inference starts anew from that point.

Even so, performing a reinitialization each time a new category appears in a frame cannot guarantee that the reinitialized frame sequence will contain all potential categories. Therefore, any method that involves resetting the memory bank upon encountering a new category will inevitably trigger a `reset_state` initialization repeatedly in long videos. This continuous resetting to avoid tensor size mismatch errors between frames due to different numbers of categories, and the subsequent loss of all previous inference results, effectively clears the memory bank each time, making it inefficient and preventing the model from benefiting from prior context in long video sequences.

We aim to allow the natural addition of new object IDs during the tracking process without resetting the entire memory bank. We achieve this by updating the memory bank online during the tracking process. To enable the inference to naturally add new object categories during the tracking process, when encountering a new object category, we need to update the following operations:

1. Register a new ID's corresponding index list and information storage dictionary in the `Inference_state`.
2. Update the memory bank of all previous frames using the new ID mapping table (reacquire `output_dict` or `temp_output_dict`, and generate the memory bank under the new ID mapping relationships through the Memory Encoder).

The schematic diagram of online updating of the memory bank during tracking is shown in 【**Figure 9**】.

![允许追踪过程中新增物体ID](./asset/允许追踪过程中新增物体ID.jpg)

【Figure9】：The schematic diagram of online memory bank updates when Det-SAM2 adds new objects during tracking. When the framework receives new object categories after initiating inference and tracking, it first registers the new object IDs in the memory bank. Subsequently, based on the updated ID mapping table, the memory bank for all previous historical frames is updated. (The batch dimension size of the information tensors in the memory bank for each frame depends on the number of IDs to be predicted. Without updating, tensor mismatches will occur, preventing the calculation of Memory Attention.)

After implementing the functionality shown in 【**Figure 9**】, we now support the ability to add new object IDs online after tracking has started. However, in long video inference, the implemented method for online updating of the memory bank processes all historical frames in the memory bank once using the memory encoder whenever it is applied. If a new object appears at the end of a long video, this approach incurs a significant computational overhead.

To improve performance efficiency, we need to impose restrictions on two components:

1. Limit the number of frames updated in the memory bank when a new object category appears.

2. Limit the number of frames used for memory attention calculation to avoid using old frames that have not been updated.

The specific approach is as follows:

1. When a new category is added during inference and tracking, only a certain number of frames close to the current moment in the memory bank are updated, while ensuring that all frames in the preload memory bank are updated.
2. Limit the number of frames used for memory attention calculation, while ensuring that all condition frames in the preload memory bank are included in the calculation.

The optimized process is shown in 【**Figure 10**】.

![允许追踪过程中新增物体ID_优化](./asset/允许追踪过程中新增物体ID_优化.jpg)

【Figure 10】：The optimized schematic diagram for online memory bank updates when new object IDs are input during the Det-SAM2 tracking process. By limiting the maximum number of frames updated in the Memory Bank and the number of condition frames used in Memory Attention calculation, while ensuring that the frames in the Preload Memory Bank are updated and involved in Memory Attention calculation, we can guarantee performance while reducing computational overhead.

#### 3.7 GPU/CPU memory optimization

SAM2【1】 official source code supports running on CPU, GPU, and NPU. However, since our own devices primarily use CPU and GPU, our optimizations mainly focus on GPU memory (VRAM) and system memory (RAM). In this section, we begin addressing the reduction of RAM and VRAM usage during the inference process in the Det-SAM2 architecture. We will introduce some interfaces reserved in the official source code, during which we will refer to many function names from the SAM2 source code.

Before optimization, the Det-SAM2 framework can infer approximately 200 video frames per 24GB of VRAM, with 6-7 segmented objects per frame. At this point, the RAM and VRAM usage increases linearly with the total number of frames in the video being processed.

1. First, we will try the first optimization interface reserved by the official source code, which is the `offload_video_to_cpu` parameter in the `SAM2VideoPredictor.init_state()` method. This parameter allows transferring the video frames in the memory bank (i.e., `inference_state["images"]`) from GPU VRAM to CPU RAM. At a video resolution of 1920x1080, this can reduce approximately 0.025GB of VRAM usage per frame, which means a reduction of 2.5GB of usage for every 100 frames.

2. Next, we will try the second optimization interface reserved by the official source code, which is the `offload_state_to_cpu` parameter in the `SAM2VideoPredictor.init_state()` method. The purpose of this parameter is to store large feature tensors, which do not require frequent computation, in CPU memory. However, in the Det-SAM2 framework we built, using this parameter does not directly save VRAM. Instead, it causes a misalignment between the generated segmentation masks and the frame indices.

   It was only after we set the tensor transfer parameter `non_blocking=False` at all locations where the `inference["storage_device"]` tensor device migration was involved that this interface started to work properly.

   ```python
   device = inference_state["storage_device"]
   tensor.to(device,non_blocking=False)
   ```

   When `offload_state_to_cpu=True`, the final effect after the fix, as mentioned in the official comments, is that VRAM is saved, while the inference time increases by approximately 22%.

3. Inspired by the discussion in the official repository issue【6】, we hope to try clearing old frame data continuously (under the condition that the old frame data will no longer be used) in order to prevent the total memory usage from increasing indefinitely. To implement this functionality, we added the `release_old_frames()` method in the `SAM2VideoPredictor` class within `sam2.sam2_video_predictor`. This method allows setting a maximum number of frames to retain (`max_inference_state_frames`). Frames that are older than the maximum retention distance from the current frame will be considered as frames to be cleared.

   Therefore, to ensure that only frames that will no longer be used are cleared, `max_inference_state_frames` should be greater than the maximum propagation length (`max_frame_num_to_track`) in `propagate_in_video()`.

   The schematic diagram of the continuous old frame clearing process is shown in 【**Figure 11**】, and the implementation of `release_old_frames()` can be found in Appendix 【**A1**】. With this approach, constant VRAM usage can be maintained during the inference process of infinitely long video frames.

   ![释放旧帧恒定显存开销](./asset/释放旧帧恒定显存开销.jpg)

   【Figure 11】：Schematic diagram of continuously releasing old frames to maintain constant VRAM usage. 

   The diagram 【**Figure 11**】 illustrates the case where the maximum number of retained frames is equal to the maximum propagation length (in the example, `max_inference_state_frames = max_frame_num_to_track = 4`). After each propagation (`propagate_in_video`), any processed frames that exceed the maximum retention limit (4 frames) will be released and cleared. In addition, the frames in the preload memory bank should never be released. Therefore, in this example (where the maximum number of retained frames equals the maximum propagation length) during the stable inference process of a long video:

   - The upper limit of VRAM usage is the data usage of `len(new_frames) + max_inference_state_frames + len(preload_memory)` frames.

   - The lower limit of VRAM usage is the data usage of `max_frame_num_to_track + len(preload_memory)` frames.

4. We unexpectedly found that the Memory Attention calculation in our pipeline generates a large number of intermediate variables that occupy VRAM and are not released in a timely manner. Therefore, we need to manually release the VRAM after the Memory Attention calculation. We discovered that this can significantly reduce the upper limit of VRAM usage in the Det-SAM2 pipeline. The specific implementation details can be found in Appendix 【**A2**】.

5. Similarly, inspired by issue 【**7**】 in the official code repository, we tried storing the images in FP16 half precision instead of the original FP32. This saves approximately 0.007GB/frame of memory at a resolution of 1920x1080, with almost no loss in segmentation mask quality.

6. To further reduce the linear growth of memory usage while keeping VRAM usage constant, we aim to continuously clear old data, including clearing the cached video frames in `inference["images"]`. Although these frames have already been offloaded to CPU memory using the `offload_video_to_cpu=True` parameter, we still want to maintain a constant memory usage for this part (at a resolution of 1920x1080, 0.025GB/frame of memory usage grows linearly).

   To implement this functionality, we need to make four changes:

   - Modify the `SAM2VideoPredictor._get_image_feature()` method, which originally directly retrieves image frames from the corresponding frame index, to instead rely on an independent index mapping list (used to record the non-continuous index relationship in the video frame tensor) to fetch the corresponding frame tensor:

     ```python
     target_idx = inference_state["images_idx"].index(frame_idx)
     image = inference_state["images"][target_idx].to(device).float().unsqueeze(0)
     ```

   - Implement the registration and updating of the `inference_state["images_idx"]` index mapping table in the `SAM2VideoPredictor.init_state()` and `update_state()` methods, respectively.

   - Add a function to clear old image frames in the `SAM2VideoPredictor.release_old_frames()` method. This will also synchronize the updates of `inference_state["images"]` and `inference_state["images_idx"]`.

   - Modify all references to `inference_state["num_frames"]` in the `SAM2VideoPredictor` class to ensure it always represents the total number of video frames that have been loaded historically, rather than the current total frame count (which may have deleted some old video frames).

7. We have already achieved constant VRAM usage, but there is still linear growth in memory usage due to the ongoing clearing of the `inference["images"]` video frame cache. How can we achieve constant memory usage? In fact, the remaining linear growth in memory usage almost entirely comes from the segmentation result dictionary `video_segments` that is continuously collected during the inference process:

   ```python
   video_segments[out_frame_idx] = {
   	out_obj_id: (out_mask_logits[i] > 0.0).cpu().numpy()
   	for i, out_obj_id in enumerate(out_obj_ids)
   }
   ```

   By simply releasing the corresponding frame in the `video_segments` dictionary after processing the segmentation results for each frame in various downstream tasks, we can achieve constant memory usage:

   ```python
   import gc
   ...
   # After your post-process in every frames
   video_segments.pop(frame_idx, None)
   gc.collect()
   ```

#### 4. Experiments

We have combined Det-SAM2 with our own business scenario example's post-processing algorithm (see Appendix 【**B1**】) to create a Det-SAM2-pipeline (see Appendix 【**B2**】). Below, we will present a visualization of the Det-SAM2-pipeline and provide an explanation.

In the context of high-speed ball movement on a billiard table, Det-SAM2 can automatically infer long videos with the original accuracy of SAM2. It can accurately track the deformation and stretching of the ball (such as the ball with ID 9 in 【**Figure 12**】), detect collisions between balls (such as the balls with IDs 9 and 17 in 【**Figure 12**】), and accurately detect when the ball bounces off the table's edge (such as the ball with ID 17 in 【**Figure 12**】).

![后处理示例](./asset/后处理示例.jpg)

【Figure 12】：The visualized post-processing result of the Det-SAM2-pipeline in our self-implemented billiard scene example is shown in 【**Figure 13**】. This image was derived from the segmentation masks predicted by SAM2, followed by post-processing. As seen, with the support of SAM2, even though the fast-moving balls are stretched in the camera frame, they are still perfectly captured.

![mask可视化](./asset/mask可视化.jpg)

【Figure 13】： Segmentation mask rendering of the Det-SAM2-pipeline in our self-implemented billiard scene example. The Det-SAM2 framework is able to maintain the original segmentation capabilities of SAM2 while operating autonomously.

#### 5. Discussion

**1.** During the implementation process, we found that the Det-SAM2 framework's frequent generation of conditional prompts for SAM2 leads to an excessive dependence on the detection model. Once some frames are missing prompts, SAM2 fails to predict segmentation results in scenarios where it could have normally performed well, with little to no additional interference. Therefore, it is necessary to carefully adjust the intervals at which the detection model is activated in custom scenarios to find the optimal parameters. We have implemented an evaluation script specifically designed to assess the best combination of parameters in example scenarios.

**2.** In the series of engineering implementations for resource optimization, we have limited the capacity of the memory bank, allowing it to store only a limited number of recent frame hints. This limitation will inevitably have an impact on videos with a large object association span. The good news is that our detection branch can consistently supply hint information for the specified object categories throughout the entire video, as a continuous and fixed pseudo-memory source. The downside is that, to ensure the best results, we still need to carefully adjust the maximum capacity of the memory bank in actual scenarios to find the optimal value. This can also be automated through a script designed to evaluate the best combination of parameters.

**3.** One issue to note is that there is a conceptual gap between the detection model and SAM2 during inference. The detection model outputs categories, and there can be multiple objects of the same category in a single frame. On the other hand, SAM2 receives object IDs, and each object ID corresponds to only one object in a frame. A limitation of our Det-SAM2 is that it can only be used in scenarios where each category can only appear once in each frame. For example, in a pool game scenario, the detection model's output needs to treat each ball as a separate category, ensuring that each ball has a unique object ID when passed to SAM2. However, if our detection model only distinguishes between the cue ball and other balls, or only between solid and striped balls, SAM2 will face the problem of receiving multiple different prompts for the same object ID at different positions, which confuses SAM2.

We have not yet resolved the gap between the detection model's output categories and SAM2's concept of receiving object IDs in Det-SAM2. Some potential solutions involve adding engineering checks to manually assign unique and fixed SAM2 object IDs to different objects of the same detection category. However, the challenge then becomes: how can we differentiate between different objects of the same detection category to ensure that their IDs remain consistently matched?

#### 6. Conclusion

This article introduces the implementation process of Det-SAM2, a framework based on SAM2 that extends the system's capabilities without requiring manual interaction. We have implemented essential features for SAM2 to be applied in specific business scenarios, enabling automatic SAM2 inference in long videos with constant GPU memory and memory usage without being affected. We believe that more applications based on SAM2 will soon emerge.

#### References

【1】Ravi, Nikhila, et al. "Sam 2: Segment anything in images and videos." *arXiv preprint arXiv:2408.00714* (2024).

【2】Kirillov, Alexander, et al. "Segment anything." *Proceedings of the IEEE/CVF International Conference on Computer Vision*. 2023.

【3】Varghese, Rejin, and M. Sambath. "YOLOv8: A Novel Object Detection Algorithm with Enhanced Performance and Robustness." *2024 International Conference on Advances in Data Engineering and Intelligent Computing Systems (ADICS)*. IEEE, 2024.

【4】Jocher, Glenn, et al. "ultralytics/yolov5: v3. 1-bug fixes and performance improvements." *Zenodo* (2020).

【5】https://github.com/facebookresearch/sam2/issues/210

【6】https://github.com/facebookresearch/sam2/issues/196#issuecomment-2286352777

【7】https://github.com/facebookresearch/sam2/issues/196#issuecomment-2475114783

#### Appendix

【A1】**Release Old Frames**

In the `sam2.sam2_video_predictor` module, the `SAM2VideoPredictor.release_old_frames()` method clears the old frames and specifically releases the non-condition frames in `output_dict` and `output_dict_per_obj`, as well as the condition frames in `output_dict`, `output_dict_per_obj`, and `consolidated_frame_inds`.

```python
def release_old_frames():
    ...
    # delate old non_cond_frames
	inference_state['output_dict']['non_cond_frame_outputs'].pop(old_idx)
	for obj in inference_state['output_dict_per_obj'].keys():
		inference_state['output_dict_per_obj'][obj]['non_cond_frame_outputs'].pop(old_idx)
	# delate old cond_framse
	inference_state['output_dict']['cond_frame_outputs'].pop(old_idx)
	inference_state['consolidated_frame_inds']['cond_frame_outputs'].discard(old_idx)
	for obj in inference_state['output_dict_per_obj'].keys():
		inference_state['output_dict_per_obj'][obj]['cond_frame_outputs'].pop(old_idx)
    ...
```

【A2】**Release GPU memory after Memory Attention.**

In the `sam2.modeling.sam2_base` module, we add a manual memory release operation after the Memory Attention calculation in the `SAM2Base._prepare_memory_conditioned_features()` method.

```python
def _prepare_memory_conditioned_features():
	...
    pix_feat_with_mem = self.memory_attention(
        curr=current_vision_feats,
        curr_pos=current_vision_pos_embeds,
        memory=memory,
        memory_pos=memory_pos_embed,
        num_obj_ptr_tokens=num_obj_ptr_tokens,
    )
    # Add release GPU memory
    torch.cuda.empty_cache()
    ...
```

【B1】**Post-processing Example**

As shown in 【**Figure 1**】, post-processing is a necessary step for Det-SAM2 to move towards higher-level applications. We have implemented a post-processing example in the billiard scene to demonstrate the potential of our Det-SAM2 in practical applications. Our post-processing example primarily designs three event detection algorithms for billiard scenes, used to determine: goals, ball-to-ball collisions, and ball rebounds off the table edges.

Specifically, in `postprocess_det_sam2.py`, we first calculate the centroid of each segmentation mask (i.e., the position coordinates of each ball) and the velocity vector of the ball between every two frames based on the masks. Using the position coordinates and velocity vectors as the foundation, we perform mid-level event detection, such as goals, collisions, and pocket bounces.

**(a) Goal Detection**

First, obtain the positions of the six pockets from the SAM2 inference backbone's detection model, assign names to the six pockets, and determine which position corresponds to which pocket.

During the traversal of each frame, the following conditions are checked:

1. The ball's position in the previous frame is near a pocket, and the ball disappears in the current frame.
2. The ball's velocity in the previous frame points towards the pocket.

If both conditions are satisfied, it is determined that the ball has entered the target pocket.

*Correction Mechanism*: If the same ball is detected entering a pocket again in subsequent frames, the latest goal information will overwrite the previous record.

**(b) Ball Collision Detection**

During the traversal of each frame, collision detection is triggered when a ball's velocity vector undergoes a significant change (exceeding a defined threshold). The following conditions are checked:

1. Identify the ball that might have collided with the current ball by analyzing the velocity vectors before and after the event:
   1.1 Before the collision, the two balls are moving towards each other.
   1.2 After the collision, the velocities of the two balls change significantly, and their accelerations exhibit correlations (e.g., the introduction of components indicating they are moving away from each other).
2. Determine if the potential collision ball is near the current ball.

If both conditions are satisfied, it is determined that a collision occurred between the two balls.

*Correction Mechanism*: If the same frame is reevaluated later and yields a different result, the new judgment will overwrite the previous information.

*Note*: Collision detection requires acceleration calculations, which necessitate data from the current frame and the two preceding frames, totaling three frames of information.

**(c) Table Edge Rebound Detection**

First, extract the four valid boundaries of the table (top, bottom, left, right) from the coordinates of the six pockets. Shrink these boundaries inward to create buffer zones near each edge, which are used to trigger rebound detection.

During the traversal of each frame, when a ball enters a buffer zone near the boundaries, the boundary position (top, bottom, left, or right) is recorded, and rebound detection is triggered based on the following conditions:

1. Check if the ball was moving toward the corresponding boundary before the rebound (in the previous frame).
2. Check if the ball is moving away from the corresponding boundary after the rebound (in the current frame).
3. Verify whether the velocity component perpendicular to the boundary has essentially reversed direction. If not, check if the velocity component parallel to the boundary remains approximately consistent.

If conditions 1, 2, and 3 are all satisfied, it is determined that the ball rebounded off the corresponding boundary.
If condition 1 is satisfied but conditions 2 and 3 are not, further checks are performed to determine if the irregular behavior is due to the ball hitting a curved surface near a pocket:

1. Check if the ball is near a pocket.
2. Determine if the velocity vector has changed significantly between the current frame and the previous frame (indicating a possible external collision).
3. Confirm that the velocity vector in the previous frame is not directed toward any other ball (to rule out ball-to-ball collisions near the pocket).
4. Verify that there are no collisions involving the ball in the current frame (using the collision results dictionary).

If conditions 4, 5, 6, and 7 are all satisfied, it is also determined that the ball rebounded off the corresponding boundary.

*Correction Mechanism*: If the same frame is reevaluated later with inconsistent results, the new judgment will overwrite the previous one.

*Note*: Rebound detection requires velocity calculations, which depend on data from the current frame and the two preceding frames, totaling three frames of information.

【B2】**Det-SAM2-pipeline**

The Det-SAM2-pipeline is a complete workflow that integrates Det-SAM2 with post-processing.

The script `Det-SAM2_pipeline.py` utilizes the video inference backbone class from `det_sam2_RT.py` and the post-processing class from `postprocess_det_sam2.py`, combining them within the `DetSAM2Pipeline.inference()` function.

During the execution of `DetSAM2Pipeline.inference()`, the SAM2 video inference backbone and the post-processing components each operate in separate threads, enabling an asynchronous and parallel workflow:

1. Main Inference Thread:

Responsible for reading data frame by frame from the video stream and performing detection and segmentation inference.

- Reads each frame from the video stream as input from the video source.
- Passes the frames into the Det-SAM2 inference framework, where the detection model provides conditional prompts for SAM2 to perform segmentation and segmentation correction in a real-time video stream.
- Stores the segmentation results of each inference (`propagate_in_video`) into the inference result cache `video_segments`. Newly added inference results are also pushed to the post-processing queue (`frames_queue`).
- Triggers the post-processing thread once the required settings (e.g., pocket coordinates, table boundaries) are collected, ensuring the post-processing thread is activated.

2. Post-Processing Thread:

Handles the segmentation results pushed by the main inference thread in parallel, performing further object tracking and state analysis.

- Monitors the post-processing queue (`frames_queue`), and starts processing as soon as new inference results are available. It processes all frames sequentially (may reprocess previously processed frames) but does not skip frames to directly process later ones.
- Uses the segmentation results retrieved from `frames_queue` to calculate the ball positions and velocity vectors.
- Performs goal detection starting from frame 2.
- Performs collision detection starting from frame 3.
- Performs rebound detection starting from frame 3.

This two-thread asynchronous parallel workflow ensures the Det-SAM2 system is efficient, accurate, and capable of real-time processing.

