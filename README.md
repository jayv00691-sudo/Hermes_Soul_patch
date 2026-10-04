## 表情包管理（Meme Pack）

Hermes Companion 现已支持轻量级表情包管理，可用于在 AI 回复中插入图片表情。

### 1. 图片存放目录

默认图片目录：

```bash
~/.hermes/companion/memes/
```

例如：

```bash
~/.hermes/companion/memes/happy/smile.png
~/.hermes/companion/memes/sad/cry.png
~/.hermes/companion/memes/shock/what.png
~/.hermes/companion/memes/laugh/laughing.png
```

分类名就是文件夹名，文件名就是图片名。

### 2. 常用命令

在 Hermes 内直接执行：

```text
/meme-list
```

列出当前所有表情分类与图片。

```text
/meme-add happy https://example.com/smile.png
```

下载并保存图片到 `happy` 分类下。

```text
/meme-del happy smile.png
```

删除某张图片。

### 3. 在回复里使用表情

在模型回复中使用下面的标记：

```text
&&happy:smile.png&&
```

或者：

```text
我今天真的很开心 &&happy:smile.png&&
```

插件会自动识别该标记，并尝试解析为对应图片路径。

### 4. 推荐图片格式

优先推荐：
- PNG
- JPG / JPEG
- WebP

建议：
- 统一使用方形图
- 推荐尺寸 512x512 或 1024x1024
- 文件名尽量使用英文和下划线，避免中文
- 图片不要过大，建议控制在 200KB ~ 2MB 以内

### 5. 发送行为

插件会先解析：

```text
&&分类名:文件名&&
```

然后尝试匹配本地图片并在 Hermes 运行环境中投递。

注意：
- 若平台支持原生图片消息发送，会直接发图
- 若平台不支持原生图片发送，会退回到文本提示/路径引用的降级方式

### 6. 示例

```text
我今天真的超开心 &&happy:smile.png&&
这件事让我有点崩溃 &&sad:cry.png&&
```

### 7. 故障排查

如果图片不显示：
1. 确认图片已放在正确目录下
2. 检查文件名和 `&&分类:文件名&&` 是否一致
3. 执行 `/meme-list` 检查是否存在
4. 检查当前 Hermes 环境是否支持图片消息发送

---

