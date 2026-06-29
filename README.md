# 圈地突围

一个基于 `pygame` 的单机 2D 缩圈竞技原型，主打中文界面、`pytmx` 驱动的多元地图、五层架构和可视化调试面板。

## 目录结构

```text
circle_siege/
  main.py
  circle_siege/
    core/          # Game、SceneManager、BaseScene、ResourceManager、配置
    entities/      # Player、BotPlayer、Weapon、Bullet、Pickup、Map
    systems/       # Camera、AI、Collision、Particles、Audio
    presentation/  # HUD 和调试 UI
    rules/         # SafeZone、MatchManager、战局播报与结算
    scenes/        # MenuScene、BattleScene、ResultScene
    maps/          # pytmx 地图加载
```

## 核心类职责

- `Game`：主循环、帧率控制、窗口与资源初始化、驱动场景
- `SceneManager`：统一管理场景切换
- `BattleScene`：战斗容器，持有 `MatchManager`、`Camera`、`HUDRenderer`
- `CharacterBase / Player / BotPlayer`：角色能力、输入或 AI
- `Weapon / Bullet / Pickup`：武器、弹道、掉落
- `Map`：地图、掩体、出生点、刷新点
- `CollisionManager`：子弹与角色/障碍的命中处理
- `MatchManager`：缩圈、生存模式规则、补给、淘汰、结算
- `ParticleSystem / Camera / AudioManager`：特效、镜头、音频接口

## 配置对象

- `GameConfig`：分辨率、FPS、音量
- `MatchConfig`：模式、时长、人数、复活规则
- `CharacterStats`：血量、护甲、速度、冲刺参数
- `WeaponData`：武器数值表
- `MapData`：地图主题与基础元数据

## 当前内容

- 全中文菜单、对局 HUD、拾取提示、战报和结算界面
- 3 套主题地图
- `赛博都市雨夜竞技场`：`cyber_city.tmx`
  背景层自动导入 `resource/img/cyber_city_bg_v5.png`
- `山村聚落`：`village1.tmx`
- `古寺遗址`：`temple1.tmx`
- `庭院迷阵`：`scene.tmx`
- 大地图、摄像机跟随、缩圈、毒圈伤害、补给投放
- 玩家射击、换弹、切枪、医疗包、拾取物资
- AI 敌人会搜刮、进圈、交战、治疗
- 调试面板和几何叠层
- 当前规则层已实现 `生存模式`
- 地图改为 `pytmx` 读取的 TMX authored 场景，支持图层、对象组、障碍、出生点、地标
- `cyber_city.tmx` 已支持 `spawn / loot / landmark / cover / trigger_supply / trigger_danger / trigger_mechanism`
- 额外支持 `trigger_capture`、重生中继、技能冷却事件、局部霓虹光区、雨滴天气层
- `trigger_supply`：进入后刷补给
- `trigger_danger`：停留时持续掉血
- `trigger_mechanism`：开启机关门并短时改变路线
- `pygame.mixer.Channel` 已分 `music / ambient / effects / ui` 通道
- 战斗场景已加局部光效层与 `BLEND_ADD` 霓虹辉光

## 当前未实现但已预留接口

- `团队竞技 / 占点模式`
- `复活逻辑`
- `技能系统 / 手雷`
- `完整设置界面`
- `真实音效资源与环境声`
- `联机同步`

## 运行

先进入项目目录：

```powershell
cd "D:\软件项目开发\circle_siege"
```

安装依赖：

```powershell
& "C:\Users\26597\AppData\Local\Programs\Python\Python313\python.exe" -m pip install -r requirements.txt
```

启动游戏：

```powershell
& "C:\Users\26597\AppData\Local\Programs\Python\Python313\python.exe" main.py
```

## 操作

- `Enter`：开始部署 / 重新开始
- `WASD`：移动
- `Shift`：冲刺
- `鼠标`：瞄准
- `左键`：开火
- `R`：换弹
- `Q`：切枪
- `F`：拾取附近物资
- `G`：使用医疗包
- `Tab`：显示/隐藏帮助面板
- `Esc`：对局中返回主菜单，菜单中退出游戏

## 调试快捷键

- `F3`：显示/隐藏调试面板
- `F4`：显示/隐藏调试几何叠层
- `F6`：在玩家附近生成空投
- `F7`：快速推进当前缩圈阶段

## 说明

- 入口文件是 [main.py](D:\软件项目开发\circle_siege\main.py)。
- 工作区根目录里还有一个 `pygame` 源码文件夹，所以请在 `circle_siege` 目录内启动本项目。
- 本项目当前使用程序化场景，不依赖外部地图解析器或额外美术资源。
