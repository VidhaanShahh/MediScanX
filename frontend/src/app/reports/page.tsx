"use client";

import { useEffect, useState } from "react";
import { api, ReportResponse } from "@/lib/api";
import { Search } from "lucide-react";
import { formatDate } from "@/lib/utils";
import Link from "next/link";

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchReports();
  }, []);

  const fetchReports = async () => {
    try {
      const res = await api.get("/api/cases").catch(() => ({ data: [] }));
      
      const allReports: ReportResponse[] = [];
      for (const c of res.data) {
        if (c.status === "completed") {
          try {
            const rRes = await api.get(`/api/reports/case/${c.id}`);
            allReports.push(...rRes.data);
          } catch (e) {}
        }
      }
      setReports(allReports.sort((a,b) => new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime()));
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadReport = async (reportId: string) => {
    try {
      const res = await api.get(`/api/reports/download/${reportId}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `report_${reportId}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error("Download failed", err);
    }
  };

  const filteredReports = reports.filter(r => 
    r.id.toLowerCase().includes(search.toLowerCase()) ||
    r.case_id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <div>
        <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">Generated Reports</h1>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center bg-slate-50 dark:bg-slate-950">
          <div className="relative w-full max-w-md">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-4 w-4 text-slate-400" />
            </div>
            <input
              type="text"
              placeholder="Search by Report ID or Case ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 w-full px-4 py-2 text-sm border border-slate-300 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-slate-400 focus:border-slate-400 bg-white dark:bg-slate-900 text-slate-900 dark:text-white transition-colors outline-none"
            />
          </div>
        </div>

        {isLoading ? (
          <div className="p-12 flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900 dark:border-white"></div>
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="p-16 text-center text-slate-500">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1">No reports found</h3>
            <p className="text-sm">Reports will appear here once generated in the case workspace.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs font-medium text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950 uppercase border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-6 py-4">Report ID</th>
                  <th className="px-6 py-4">Case ID</th>
                  <th className="px-6 py-4">Generated At</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {filteredReports.map((report) => (
                  <tr key={report.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                    <td className="px-6 py-4 font-mono text-xs text-slate-900 dark:text-white">{report.id}</td>
                    <td className="px-6 py-4 font-mono text-xs text-slate-900 dark:text-white">
                      <Link href={`/cases/${report.case_id}`} className="hover:underline">
                        {report.case_id}
                      </Link>
                    </td>
                    <td className="px-6 py-4 text-slate-500 text-xs font-medium">{formatDate(report.generated_at)}</td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => handleDownloadReport(report.id)}
                        className="text-sm font-medium text-slate-900 dark:text-white hover:underline text-xs uppercase tracking-wide"
                      >
                        Download
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
