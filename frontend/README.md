# StudyMate — 全栈学习管理平台

StudyMate 是一个面向个人学习场景的学习管理平台，帮助用户管理学习笔记、规划学习任务、记录每日打卡，并通过专注计时与学习统计追踪学习进度。

## 项目功能

- **学习笔记管理**：创建、搜索、编辑和删除学习笔记。
- **学习任务管理**：管理学习任务及完成状态。
- **每日学习打卡**：使用打卡日历记录学习日期和连续打卡情况。
- **专注计时**：辅助用户进行专注学习。
- **学习统计仪表盘**：汇总学习数据，查看学习进度。
- **成就徽章**：根据学习情况展示成就和进度。
- **数据持久化**：使用 SQLite 保存数据，通过后端 API 读写数据。

## 技术栈

### 前端
- React
- TypeScript
- Vite
- CSS

### 后端
- Python
- FastAPI
- SQLAlchemy
- SQLite

### 开发工具
- Git
- npm
- Python 虚拟环境

## 项目结构

```text
StudyMate/
├── main.py
├── studymate.db
├── .gitignore
└── frontend/
    ├── public/
    ├── src/
    │   ├── App.tsx
    │   ├── App.css
    │   ├── CheckinPanel.tsx
    │   ├── DashboardPanel.tsx
    │   ├── DashboardPanel.css
    │   ├── AchievementsPanel.tsx
    │   ├── AchievementsPanel.css
    │   ├── TimerPanel.tsx
    │   ├── TimerPanel.css
    │   └── main.tsx
    ├── package.json
    └── vite.config.ts
```

## 环境要求

- Python
- Node.js 和 npm
- Git

## 本地运行

### 1. 启动后端

在项目根目录 `StudyMate/` 打开 PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload
```

后端默认地址：

- API 地址：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs

### 2. 启动前端

另开一个终端，进入前端目录：

```powershell
cd frontend
npm install
npm run dev
```

按照终端输出的本地地址打开网页，默认通常为：

http://localhost:5173/

### 3. 构建前端

在 `frontend/` 目录执行：

```powershell
npm run build
```

## 数据存储

项目使用 SQLite 保存学习数据。数据库文件由后端配置决定，当前开发环境使用本地数据库。

请勿随意删除数据库文件，以免丢失学习笔记、任务或其他学习记录。

## 当前开发状态

- [x] 前后端本地运行
- [x] 前端 TypeScript 检查与生产构建
- [x] Git 初始版本提交
- [x] 学习笔记管理
- [x] 学习统计、打卡、专注计时与成就界面

## 后续改进计划

- 增加用户注册与登录
- 补充后端接口和业务逻辑测试
- 完善异常处理与输入校验
- 优化移动端适配
- 部署上线并补充项目演示截图

## 项目目的

本项目用于学习和实践前后端分离开发、REST API、关系型数据库操作、前端状态管理及 Git 版本管理等开发流程。