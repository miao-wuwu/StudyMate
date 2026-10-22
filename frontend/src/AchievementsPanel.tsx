
import { useCallback, useEffect, useMemo, useState } from "react";
import "./AchievementsPanel.css";

const API_URL = "http://127.0.0.1:8000";

type Task = {
  id: number;
  title: string;
  due_date: string;
  category: string;
  completed: boolean;
};

type CheckinData = {
  dates: string[];
  total: number;
  streak: number;
  checked_today: boolean;
  today: string;
};

type StudySession = {
  id: number;
  task_id: number | null;
  task_title: string;
  duration_minutes: number;
  started_at: string;
  completed_at: string;
  study_date: string;
};

type Note = {
  id: number;
  title: string;
  content: string;
  category: string;
};

function AchievementCard({
  icon,
  title,
  description,
  unlocked,
  progress,
}: {
  icon: string;
  title: string;
  description: string;
  unlocked: boolean;
  progress: string;
}) {
  return (
    <article className={`achievement-card ${unlocked ? "unlocked" : ""}`}>
      <div className="achievement-icon">{icon}</div>

      <div className="achievement-content">
        <h3>{title}</h3>
        <p>{description}</p>

        <span className={`achievement-status ${unlocked ? "done" : ""}`}>
          {unlocked ? "✓ 已解锁" : progress}
        </span>
      </div>
    </article>
  );
}

export default function AchievementsPanel() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [checkins, setCheckins] = useState<CheckinData | null>(null);
  const [sessions, setSessions] = useState<StudySession[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const responses = await Promise.all([
        fetch(`${API_URL}/tasks`),
        fetch(`${API_URL}/checkins`),
        fetch(`${API_URL}/study-sessions?limit=200`),
        fetch(`${API_URL}/notes`),
      ]);

      if (responses.some((response) => !response.ok)) {
        throw new Error("读取成就数据失败，请检查后端服务。");
      }

      const [taskData, checkinData, sessionData, noteData] =
        await Promise.all(responses.map((response) => response.json()));

      setTasks(taskData);
      setCheckins(checkinData);
      setSessions(sessionData);
      setNotes(noteData);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "无法读取成就数据。",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = useMemo(() => {
    const completedTasks = tasks.filter(
      (task) => task.completed,
    ).length;

    const minutes = sessions.reduce(
      (sum, session) => sum + session.duration_minutes,
      0,
    );

    return {
      completedTasks,
      minutes,
      count: sessions.length,
      notes: notes.length,
      streak: checkins?.streak ?? 0,
      checkins: checkins?.total ?? 0,
    };
  }, [tasks, sessions, notes, checkins]);

  const achievements = [
    {
      icon: "🌱",
      title: "初次打卡",
      description: "记录第一次学习打卡。",
      unlocked: stats.checkins >= 1,
      progress: `累计打卡 ${Math.min(stats.checkins, 1)}/1 天`,
    },
    {
      icon: "🔥",
      title: "坚持一周",
      description: "连续打卡 7 天。",
      unlocked: stats.streak >= 7,
      progress: `连续打卡 ${Math.min(stats.streak, 7)}/7 天`,
    },
    {
      icon: "🏆",
      title: "学习达人",
      description: "连续打卡 30 天。",
      unlocked: stats.streak >= 30,
      progress: `连续打卡 ${Math.min(stats.streak, 30)}/30 天`,
    },
    {
      icon: "⏱️",
      title: "初次专注",
      description: "完成第一次专注计时。",
      unlocked: stats.count >= 1,
      progress: `完成专注 ${Math.min(stats.count, 1)}/1 次`,
    },
    {
      icon: "🍅",
      title: "番茄起步",
      description: "累计专注达到 5 次。",
      unlocked: stats.count >= 5,
      progress: `完成专注 ${Math.min(stats.count, 5)}/5 次`,
    },
    {
      icon: "🌳",
      title: "专注 5 小时",
      description: "累计专注达到 300 分钟。",
      unlocked: stats.minutes >= 300,
      progress: `累计专注 ${Math.min(stats.minutes, 300)}/300 分钟`,
    },
    {
      icon: "🚀",
      title: "专注 20 小时",
      description: "累计专注达到 1200 分钟。",
      unlocked: stats.minutes >= 1200,
      progress: `累计专注 ${Math.min(stats.minutes, 1200)}/1200 分钟`,
    },
    {
      icon: "✅",
      title: "第一个任务",
      description: "完成第一个学习任务。",
      unlocked: stats.completedTasks >= 1,
      progress: `完成任务 ${Math.min(stats.completedTasks, 1)}/1 个`,
    },
    {
      icon: "🎯",
      title: "任务达人",
      description: "完成 20 个学习任务。",
      unlocked: stats.completedTasks >= 20,
      progress: `完成任务 ${Math.min(stats.completedTasks, 20)}/20 个`,
    },
    {
      icon: "📚",
      title: "知识收藏家",
      description: "累计保存 10 篇学习笔记。",
      unlocked: stats.notes >= 10,
      progress: `保存笔记 ${Math.min(stats.notes, 10)}/10 篇`,
    },
  ];

  const unlockedCount = achievements.filter(
    (item) => item.unlocked,
  ).length;

  return (
    <section className="achievements-page">
      <header className="achievements-hero">
        <span className="achievements-eyebrow">
          YOUR LEARNING MILESTONES
        </span>

        <h2>学习成就</h2>

        <p>
          每一次打卡、每一段专注和每一个完成的任务，
          都在积累你的成长。
        </p>

        <div className="achievements-overview">
          <strong>
            {loading ? "—" : unlockedCount}
            <small> / {achievements.length}</small>
          </strong>

          <span>项成就已解锁</span>

          <div className="achievements-overview-track">
            <div
              style={{
                width: `${(unlockedCount / achievements.length) * 100}%`,
              }}
            />
          </div>
        </div>
      </header>

      {error && (
        <p className="achievements-error" role="alert">
          {error}
        </p>
      )}

      <div className="achievements-stats">
        <div>
          <span>连续打卡</span>
          <strong>
            {loading ? "—" : `${stats.streak} 天`}
          </strong>
        </div>

        <div>
          <span>累计专注</span>
          <strong>
            {loading ? "—" : `${stats.minutes} 分钟`}
          </strong>
        </div>

        <div>
          <span>完成任务</span>
          <strong>
            {loading ? "—" : `${stats.completedTasks} 个`}
          </strong>
        </div>

        <div>
          <span>学习笔记</span>
          <strong>
            {loading ? "—" : `${stats.notes} 篇`}
          </strong>
        </div>
      </div>

      <div className="achievements-heading">
        <div>
          <span className="achievements-eyebrow">
            BADGE COLLECTION
          </span>
          <h3>我的徽章墙</h3>
          <p>
            尚未解锁的徽章会显示进度，达成条件后自动点亮。
          </p>
        </div>

        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
        >
          {loading ? "更新中…" : "↻ 刷新"}
        </button>
      </div>

      <div className="achievement-grid">
        {achievements.map((item) => (
          <AchievementCard key={item.title} {...item} />
        ))}
      </div>

      <p className="achievements-note">
        成就根据当前数据库中的打卡、专注记录、任务和笔记自动计算，
        不需要额外创建成就表，也不会修改或删除现有记录。
      </p>
    </section>
  );
}
