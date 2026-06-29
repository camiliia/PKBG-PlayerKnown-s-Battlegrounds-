# TMX 地图编辑器

这个工具用于编辑 `D:\软件项目开发\resource\tmx` 目录下的 TMX 地图对象组，适合手工摆放障碍、掉落点、出生点和触发区。

## 启动

在项目根目录执行：

```powershell
cd "D:\软件项目开发\circle_siege"
& "C:\Users\26597\AppData\Local\Programs\Python\Python313\python.exe" map_editor.py --map cyber_city.tmx
```

也可以直接运行：

```powershell
& "C:\Users\26597\AppData\Local\Programs\Python\Python313\python.exe" tools\tmx_editor.py --map cyber_city.tmx
```

如果不传 `--map`，默认优先打开 `cyber_city.tmx`。

## 当前支持的对象组

- `obstacle`：矩形障碍
- `loot`：物品掉落点
- `spawn`：出生点
- `cover`：掩体点
- `landmark`：地标点
- `trigger_supply`：补给触发区
- `trigger_danger`：危险触发区
- `trigger_mechanism`：机关触发区

说明：

- 这些对象会直接保存回原始 TMX。
- 其他未支持的图层和对象组会保留，不会被编辑器主动删除。
- 每次保存会在同目录生成一个 `.tmx.bak` 备份文件。

## 鼠标操作

- 左键空白处：新增当前图层对象
- 左键已有对象：选中并拖动
- 拖动矩形右下角手柄：调整矩形障碍或触发区大小
- 右键对象：删除
- 中键，或 `空格 + 左键`：拖动画布
- 滚轮：缩放画布

## 键盘快捷键

- `1` 到 `8`：切换当前编辑图层
- `Ctrl + S`：保存
- `F5`：放弃未保存修改并重载当前地图
- `PageUp / PageDown`：切换地图
- `Delete / Backspace`：删除当前选中对象
- `Ctrl + D`：复制当前选中对象
- `方向键`：微调位置
- `Shift + 方向键`：按 10 像素微调位置
- `Alt + 方向键`：调整矩形对象尺寸
- `G`：显示/隐藏网格
- `F`：重新居中地图
- `Esc`：取消当前绘制或拖动

## 适合当前项目的用法

1. 先在编辑器里打开目标 TMX。
2. 用 `obstacle` 画出碰撞区域。
3. 用 `loot` 摆放武器、物资、藏宝图候选掉落点。
4. 用 `spawn` 摆出生点。
5. 保存后直接回游戏测试，无需转换格式。
