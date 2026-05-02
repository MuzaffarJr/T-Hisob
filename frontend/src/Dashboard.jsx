import { useEffect, useState } from "react";
import axios from "axios";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
  ArcElement,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Tooltip, Legend);

const fmt = (n) =>
  new Intl.NumberFormat("uz-UZ").format(Math.round(n));

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [categories, setCategories] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [telegramId, setTelegramId] = useState(null);

  useEffect(() => {
    // Telegram ID ni olish (WebApp uchun)
    const tg = window.Telegram?.WebApp;
    if (tg?.initDataUnsafe?.user?.id) {
      setTelegramId(tg.initDataUnsafe.user.id);
    }
  }, []);

  useEffect(() => {
    if (!telegramId) return;
    
    Promise.all([
      axios.get("http://localhost:8000/reports/pnl", {
        headers: { "ngrok-skip-browser-warning": "any" },
      }),
      axios.get(`http://localhost:8000/reports/categories?telegram_id=${telegramId}`, {
        headers: { "ngrok-skip-browser-warning": "any" },
      }),
    ])
      .then(([pnlRes, catRes]) => {
        setData(pnlRes.data);
        setCategories(catRes.data);
      })
      .catch(() => setError("Backend bilan ulanishda xatolik"))
      .finally(() => setLoading(false));
  }, [telegramId]);

  if (loading)
    return (
      <div className="flex items-center justify-center h-screen text-slate-500">
        Yuklanmoqda...
      </div>
    );

  if (error)
    return (
      <div className="flex items-center justify-center h-screen text-red-500">
        {error}
      </div>
    );

  const chartData = {
    labels: data.chart.labels,
    datasets: [
      {
        label: "Kirim",
        data: data.chart.kirim,
        backgroundColor: "rgba(34, 197, 94, 0.7)",
        borderRadius: 4,
      },
      {
        label: "Chiqim",
        data: data.chart.chiqim,
        backgroundColor: "rgba(239, 68, 68, 0.7)",
        borderRadius: 4,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    plugins: { legend: { position: "top" } },
    scales: {
      y: {
        ticks: {
          callback: (v) => fmt(v),
        },
      },
    },
  };

  const doughnutData = categories ? {
    labels: categories.categories.map(c => c.name),
    datasets: [
      {
        label: "Xarajatlar",
        data: categories.categories.map(c => c.amount),
        backgroundColor: [
          "rgba(239, 68, 68, 0.7)",
          "rgba(245, 158, 11, 0.7)",
          "rgba(59, 130, 246, 0.7)",
          "rgba(139, 92, 246, 0.7)",
          "rgba(236, 72, 153, 0.7)",
        ],
        borderColor: [
          "rgba(239, 68, 68, 1)",
          "rgba(245, 158, 11, 1)",
          "rgba(59, 130, 246, 1)",
          "rgba(139, 92, 246, 1)",
          "rgba(236, 72, 153, 1)",
        ],
        borderWidth: 2,
      },
    ],
  } : null;

  const doughnutOptions = {
    responsive: true,
    plugins: {
      legend: { position: "bottom" },
      tooltip: {
        callbacks: {
          label: (ctx) => `${ctx.label}: ${fmt(ctx.parsed)} so'm (${ctx.dataset.data.length > 0 ? ((ctx.parsed / categories.total) * 100).toFixed(1) : 0}%)`,
        },
      },
    },
  };

  return (
    <div
      className="min-h-screen p-4"
      style={{ backgroundColor: "#f3f4f6", fontFamily: "system-ui, sans-serif" }}
    >
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-800">T-Hisob Dashboard</h1>
          <p className="text-sm text-slate-500 italic">{data.month}</p>
        </div>
        <div className="bg-blue-100 p-2 rounded-full">
          <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
      </div>

      {/* Balance kartalar */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <Card>
          <p className="text-xs text-slate-500 mb-1">Sof Foyda</p>
          <p className={`text-lg font-bold ${data.sof_foyda >= 0 ? "text-green-600" : "text-red-500"}`}>
            {data.sof_foyda >= 0 ? "+" : ""}{fmt(data.sof_foyda)} so'm
          </p>
        </Card>
        <Card className="border-l-4 border-orange-400">
          <p className="text-xs text-slate-500 mb-1">Soliq Prognozi (4%)</p>
          <p className="text-lg font-bold text-slate-800">{fmt(data.soliq)} so'm</p>
        </Card>
        <Card>
          <p className="text-xs text-slate-500 mb-1">Umumiy Kirim</p>
          <p className="text-lg font-bold text-green-600">{fmt(data.total_kirim)} so'm</p>
        </Card>
        <Card>
          <p className="text-xs text-slate-500 mb-1">Umumiy Chiqim</p>
          <p className="text-lg font-bold text-red-500">{fmt(data.total_chiqim)} so'm</p>
        </Card>
      </div>

      {/* Bar Grafik */}
      <Card className="mb-6 p-4">
        <div className="flex justify-between items-center mb-4">
          <h2 className="font-semibold text-slate-700 text-sm">Oylik Tahlil — Kirim vs Chiqim</h2>
          <span className="text-xs text-blue-600">{data.month}</span>
        </div>
        <Bar data={chartData} options={chartOptions} />
      </Card>

      {/* Xarajatlar Doughnut Chart */}
      {doughnutData && (
        <Card className="mb-6 p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-semibold text-slate-700 text-sm">Xarajatlar Kategoriyalar Bo'yicha</h2>
            <span className="text-xs text-red-600">{fmt(categories.total)} so'm</span>
          </div>
          <div style={{ maxHeight: "300px", display: "flex", justifyContent: "center" }}>
            <Doughnut data={doughnutData} options={doughnutOptions} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
            {categories.categories.map((cat, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <div
                  style={{
                    width: "8px",
                    height: "8px",
                    backgroundColor: [
                      "rgba(239, 68, 68, 0.7)",
                      "rgba(245, 158, 11, 0.7)",
                      "rgba(59, 130, 246, 0.7)",
                      "rgba(139, 92, 246, 0.7)",
                      "rgba(236, 72, 153, 0.7)",
                    ][idx % 5],
                    borderRadius: "50%",
                  }}
                />
                <span className="text-slate-600">{cat.name}: {cat.percentage}%</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* P&L jadvali */}
      <Card className="p-4">
        <h2 className="font-semibold text-slate-700 text-sm mb-3">P&L Xulosasi</h2>
        <div className="space-y-2 text-sm">
          <Row label="Umumiy Kirim" value={`${fmt(data.total_kirim)} so'm`} color="text-green-600" />
          <Row label="Umumiy Chiqim" value={`${fmt(data.total_chiqim)} so'm`} color="text-red-500" />
          <div className="border-t border-slate-200 pt-2 mt-2">
            <Row label="Sof Foyda" value={`${fmt(data.sof_foyda)} so'm`}
              color={data.sof_foyda >= 0 ? "text-green-700" : "text-red-600"} bold />
            <Row label="Taxminiy Soliq (4%)" value={`${fmt(data.soliq)} so'm`} color="text-orange-500" />
          </div>
        </div>
      </Card>
    </div>
  );
}

function Card({ children, className = "" }) {
  return (
    <div
      className={`bg-white p-4 ${className}`}
      style={{ borderRadius: 16, boxShadow: "0 4px 6px -1px rgba(0,0,0,0.1)" }}
    >
      {children}
    </div>
  );
}

function Row({ label, value, color, bold }) {
  return (
    <div className="flex justify-between">
      <span className={`text-slate-500 ${bold ? "font-semibold" : ""}`}>{label}</span>
      <span className={`${color} ${bold ? "font-bold" : "font-medium"}`}>{value}</span>
    </div>
  );
}
