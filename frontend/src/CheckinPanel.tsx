
import { useCallback, useEffect, useMemo, useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

type CheckinData = {
  dates: string[];
  total: number;
  streak: number;
  checked_today: boolean;
  today: string;
};

function getToday() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function CheckinPanel() {
  const [data, setData] = useState<CheckinData | null>(null);
  const [month, setMonth] = useState(() => {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/checkins`);
      if (!response.ok) throw new Error("读取打卡记录失败");
      setData(await response.json());
    } catch {
      setMessage("无法读取打卡数据，请检查后端服务。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const checkedDates = useMemo(
    () => new Set(data?.dates ?? []),
    [data]
  );

  const calendar = useMemo(() => {
    const [year, monthNumber] = month.split("-").map(Number);
    const firstWeekday = new Date(year, monthNumber - 1, 1).getDay();
    const daysInMonth = new Date(year, monthNumber, 0).getDate();

    return [
      ...Array.from({ length: firstWeekday }, () => null as number | null),
      ...Array.from({ length: daysInMonth }, (_, index) => index + 1),
    ];
  }, [month]);

  function changeMonth(offset: number) {
    const [year, monthNumber] = month.split("-").map(Number);
    const next = new Date(year, monthNumber - 1 + offset, 1);
    setMonth(
      `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`
    );
  }

  async function toggleToday() {
    if (!data || busy) return;

    setBusy(true);
    setMessage("");

    try {
      const response = await fetch(`${API_URL}/checkins/today`, {
        method: data.checked_today ? "DELETE" : "POST",
      });

      if (!response.ok) throw new Error("更新打卡状态失败");

      const result = await response.json();
      setMessage(result.message);
      await loadData();
    } catch {
      setMessage("打卡操作失败，请检查后端服务。");
    } finally {
      setBusy(false);
    }
  }

  const [yearNumber, monthNumber] = month.split("-").map(Number);
  
  const trendDays = useMemo(() => {
    const dates = new Set(data?.dates ?? []);

    return Array.from({ length: 7 }, (_, index) => {
      const day = new Date();
      day.setHours(0, 0, 0, 0);
      day.setDate(day.getDate() - (6 - index));

      const key = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;

      return {
        key,
        label: `${day.getMonth() + 1}/${day.getDate()}`,
        checked: dates.has(key),
      };
    });
  }, [data]);


  return (
    <section className="checkin-page">
      <div className="checkin-hero">
        <span className="section-kicker">YOUR LEARNING HABIT</span>
        <h2>每天进步一点点</h2>
        <p>坚持学习不必追求完美，今天开始就很好。</p>

        <div className="checkin-today">
          <div>
            <span className="checkin-date-label">今天是</span>
            <strong>{data?.today ?? getToday()}</strong>
          </div>
          <button
            type="button"
            className={`checkin-button ${data?.checked_today ? "checked" : ""}`}
            onClick={() => void toggleToday()}
            disabled={loading || busy || !data}
          >
            {busy ? "处理中…" : data?.checked_today ? "✓ 今日已打卡" : "今日打卡 →"}
          </button>
        </div>

        {message && <p className="status-message" role="status">{message}</p>}
        {data?.checked_today && (
          <p className="checkin-encouragement">今天也为自己的进步留下了记录！</p>
        )}
      </div>

      <div className="checkin-stats">
        <article className="checkin-stat-card">
          <span>累计打卡</span>
          <strong>{loading ? "—" : data?.total ?? 0}</strong>
          <small>记录下来的学习日</small>
        </article>
        <article className="checkin-stat-card">
          <span>连续学习</span>
          <strong>{loading ? "—" : data?.streak ?? 0}</strong>
          <small>连续打卡天数</small>
        </article>
        <article className="checkin-stat-card">
          <span>本月打卡</span>
          <strong>
            {loading ? "—" : (data?.dates ?? []).filter((d) => d.startsWith(month)).length}
          </strong>
          <small>本月已记录的天数</small>
        </article>
      </div>


      <div className="checkin-achievements">
        <div className="checkin-achievements-heading">
          <span className="section-kicker">YOUR ACHIEVEMENTS</span>
          <h3>我的学习成就</h3>
          <p>每一次坚持，都值得被记录。</p>
        </div>

        <div className="checkin-badges">
          <article className={`checkin-badge-card ${(data?.total ?? 0) >= 1 ? "unlocked" : ""}`}>
            <div className="checkin-badge-icon">🌱</div>
            <h4>初次打卡</h4>
            <p>完成第一次打卡</p>
            <span>{(data?.total ?? 0) >= 1 ? "✓ 已解锁" : "累计打卡 1 天"}</span>
          </article>

          <article className={`checkin-badge-card ${(data?.streak ?? 0) >= 7 ? "unlocked" : ""}`}>
            <div className="checkin-badge-icon">🔥</div>
            <h4>坚持一周</h4>
            <p>连续打卡 7 天</p>
            <span>{(data?.streak ?? 0) >= 7 ? "✓ 已解锁" : "连续打卡 7 天"}</span>
          </article>

          <article className={`checkin-badge-card ${(data?.streak ?? 0) >= 30 ? "unlocked" : ""}`}>
            <div className="checkin-badge-icon">🏆</div>
            <h4>学习达人</h4>
            <p>连续打卡 30 天</p>
            <span>{(data?.streak ?? 0) >= 30 ? "✓ 已解锁" : "连续打卡 30 天"}</span>
          </article>
        </div>
      </div>


      <div className="checkin-trend-panel">
        <div className="checkin-trend-heading">
          <div>
            <span className="section-kicker">YOUR WEEKLY PROGRESS</span>
            <h3>最近 7 天打卡趋势</h3>
            <p>每天进步一点点，积累就是成长。</p>
          </div>
          <div className="trend-summary">
            <strong>{trendDays.filter((day) => day.checked).length}<span>/7</span></strong>
            <small>天已打卡</small>
          </div>
        </div>

        <div className="checkin-trend-chart">
          {trendDays.map((day) => (
            <div className="trend-day" key={day.key}>
              <div className="trend-bar-area">
                <div
                  className={`trend-bar ${day.checked ? "trend-bar-done" : ""}`}
                  style={{ height: day.checked ? "100%" : "12%" }}
                  title={day.checked ? `${day.key} 已打卡` : `${day.key} 未打卡`}
                />
              </div>
              <span className="trend-day-label">{day.label}</span>
              <span className="trend-day-status">
                {day.checked ? "✓" : "—"}
              </span>
            </div>
          ))}
        </div>

        <div className="trend-chart-legend">
          <span><i className="legend-dot legend-done" /> 已打卡</span>
          <span><i className="legend-dot legend-today" /> 未打卡</span>
        </div>
      </div>


      <div className="checkin-calendar-panel">
        <div className="checkin-calendar-heading">
          <div>
            <span className="section-kicker">YOUR CALENDAR</span>
            <h3>学习打卡日历</h3>
          </div>
          <div className="calendar-navigation">
            <button type="button" onClick={() => changeMonth(-1)} aria-label="上个月">‹</button>
            <strong>{yearNumber}年{monthNumber}月</strong>
            <button type="button" onClick={() => changeMonth(1)} aria-label="下个月">›</button>
          </div>
        </div>

        <div className="checkin-calendar-grid">
          {["日", "一", "二", "三", "四", "五", "六"].map((day) => (
            <div className="calendar-weekday" key={day}>{day}</div>
          ))}

          {calendar.map((day, index) => {
            if (day === null) {
              return <div className="calendar-empty" key={`empty-${index}`} />;
            }

            const dateString = `${month}-${String(day).padStart(2, "0")}`;
            const checked = checkedDates.has(dateString);
            const isToday = dateString === getToday();

            return (
              <div
                key={dateString}
                className={`calendar-day ${checked ? "calendar-checked" : ""} ${isToday ? "calendar-today" : ""}`}
                title={checked ? `${dateString} 已打卡` : dateString}
              >
                <span>{day}</span>
                {checked && <span className="calendar-check-mark">✓</span>}
              </div>
            );
          })}
        </div>

        <div className="calendar-legend">
          <span><i className="legend-dot legend-done" /> 已打卡</span>
          <span><i className="legend-dot legend-today" /> 今天</span>
        </div>
      </div>

      <div className="checkin-tip-panel">
        <span className="checkin-tip-icon">✦</span>
        <div>
          <h3>给自己的小提醒</h3>
          <p>学习不需要每天都很努力，只要愿意持续开始，就值得为自己点赞。</p>
        </div>
      </div>
    </section>
  );
}

export default CheckinPanel;
