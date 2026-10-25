"use client";

import { useEffect, useState, useRef } from "react";
import { api, ReportResponse } from "@/lib/api";
import { Search, Eye, Download, Printer, X, AlertCircle, FileText, Loader2, CheckCircle2 } from "lucide-react";
import { formatDate } from "@/lib/utils";
import Link from "next/link";

interface ReportModalData {
  reportId: string;
  blobUrl: string;
}

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // Action states for specific report rows
  const [actionLoading, setActionLoading] = useState<{ [reportId: string]: "view" | "download" | null }>({});
  const [actionError, setActionError] = useState<{ [reportId: string]: string | null }>({});

  // Active Report Viewer Modal state
  const [activeReportModal, setActiveReportModal] = useState<ReportModalData | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    fetchReports();
  }, []);

  const fetchReports = async () => {
    setIsLoading(true);
    setPageError(null);
    try {
      // 1. Try dedicated endpoint first
      const res = await api.get("/api/reports");
      setReports(res.data.sort((a: ReportResponse, b: ReportResponse) => new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime()));
    } catch (primaryErr: any) {
      console.warn("Direct GET /api/reports failed, falling back to case crawling:", primaryErr);
      try {
        const cRes = await api.get("/api/cases").catch(() => ({ data: [] }));
        const allReports: ReportResponse[] = [];
        for (const c of cRes.data) {
          try {
            const rRes = await api.get(`/api/reports/case/${c.id}`);
            allReports.push(...rRes.data);
          } catch (e) {}
        }
        setReports(allReports.sort((a, b) => new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime()));
      } catch (fallbackErr: any) {
        setPageError(primaryErr.response?.data?.detail || primaryErr.message || "Failed to load reports catalogue.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadReport = async (reportId: string) => {
    setActionLoading((prev) => ({ ...prev, [reportId]: "download" }));
    setActionError((prev) => ({ ...prev, [reportId]: null }));
    try {
      const res = await api.get(`/api/reports/download/${reportId}`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `report_${reportId}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => window.URL.revokeObjectURL(url), 10000);
    } catch (err: any) {
      let errMsg = "Download failed. Please check permissions.";
      if (err.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          if (json.detail) errMsg = json.detail;
        } catch (_) {}
      } else if (err.response?.data?.detail) {
        errMsg = err.response.data.detail;
      }
      setActionError((prev) => ({ ...prev, [reportId]: errMsg }));
    } finally {
      setActionLoading((prev) => ({ ...prev, [reportId]: null }));
    }
  };

  const handleViewReport = async (reportId: string) => {
    setActionLoading((prev) => ({ ...prev, [reportId]: "view" }));
    setActionError((prev) => ({ ...prev, [reportId]: null }));
    try {
      const res = await api.get(`/api/reports/view/${reportId}`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const blobUrl = window.URL.createObjectURL(blob);
      setActiveReportModal({
        reportId,
        blobUrl,
      });
    } catch (err: any) {
      let errMsg = "Unable to view report. File may be unavailable or unauthorized.";
      if (err.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          if (json.detail) errMsg = json.detail;
        } catch (_) {}
      } else if (err.response?.data?.detail) {
        errMsg = err.response.data.detail;
      }
      setActionError((prev) => ({ ...prev, [reportId]: errMsg }));
    } finally {
      setActionLoading((prev) => ({ ...prev, [reportId]: null }));
    }
  };

  const handleCloseModal = () => {
    if (activeReportModal?.blobUrl) {
      window.URL.revokeObjectURL(activeReportModal.blobUrl);
    }
    setActiveReportModal(null);
  };

  const handlePrintModalReport = () => {
    if (!iframeRef.current) return;
    try {
      const iframeWin = iframeRef.current.contentWindow;
      if (iframeWin) {
        iframeWin.focus();
        iframeWin.print();
        return;
      }
    } catch (e) {
      console.warn("Direct iframe print failed, falling back to window.open print", e);
    }
    // Fallback if cross-origin or sandbox limits iframe print
    if (activeReportModal?.blobUrl) {
      const printWin = window.open(activeReportModal.blobUrl, "_blank");
      if (printWin) {
        printWin.focus();
        printWin.print();
      }
    }
  };

  const filteredReports = reports.filter(
    (r) =>
      r.id.toLowerCase().includes(search.toLowerCase()) ||
      r.case_id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">Generated Reports</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Browse, inspect, print, and securely download authenticated medical reports.
          </p>
        </div>
      </div>

      {pageError && (
        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-700 dark:text-red-400 text-sm flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <span>{pageError}</span>
          </div>
          <button
            onClick={fetchReports}
            className="text-xs bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded font-semibold transition"
          >
            Retry
          </button>
        </div>
      )}

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden shadow-sm">
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
              className="pl-9 w-full px-4 py-2 text-sm border border-slate-300 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-teal-500 focus:border-teal-500 bg-white dark:bg-slate-900 text-slate-900 dark:text-white transition-colors outline-none"
            />
          </div>
        </div>

        {isLoading ? (
          <div className="p-16 flex flex-col items-center justify-center space-y-3">
            <Loader2 className="w-8 h-8 animate-spin text-teal-600 dark:text-teal-400" />
            <p className="text-sm text-slate-500">Retrieving diagnostic reports from database...</p>
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="p-16 text-center text-slate-500">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1">No reports found</h3>
            <p className="text-sm">Reports will appear here once generated in the case workspace.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs font-semibold text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950 uppercase border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-6 py-4">Report ID</th>
                  <th className="px-6 py-4">Case ID</th>
                  <th className="px-6 py-4">SHA-256 Digest</th>
                  <th className="px-6 py-4">Generated At</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {filteredReports.map((report) => {
                  const isCurrentRowLoading = actionLoading[report.id];
                  const currentRowError = actionError[report.id];

                  return (
                    <tr key={report.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                      <td className="px-6 py-4 font-mono text-xs text-slate-900 dark:text-white font-medium">
                        {report.id}
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-teal-600 dark:text-teal-400">
                        <Link href={`/cases/${report.case_id}`} className="hover:underline flex items-center space-x-1">
                          <span>{report.case_id}</span>
                        </Link>
                      </td>
                      <td
                        className="px-6 py-4 font-mono text-[11px] text-slate-500 max-w-[200px] truncate"
                        title={report.sha256 || "Legacy report without recorded digest"}
                      >
                        {report.sha256 ? `${report.sha256.slice(0, 16)}...` : "None"}
                      </td>
                      <td className="px-6 py-4 text-slate-500 text-xs font-medium">
                        {formatDate(report.generated_at)}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex flex-col items-end space-y-1">
                          <div className="flex items-center space-x-2">
                            <button
                              onClick={() => handleViewReport(report.id)}
                              disabled={!!isCurrentRowLoading}
                              className="inline-flex items-center space-x-1.5 px-2.5 py-1.5 rounded-md text-xs font-semibold bg-teal-50 hover:bg-teal-100 dark:bg-teal-950/60 dark:hover:bg-teal-900 text-teal-700 dark:text-teal-300 border border-teal-200 dark:border-teal-800/70 transition disabled:opacity-50"
                              title="Inspect and print report in viewer"
                            >
                              {isCurrentRowLoading === "view" ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Eye className="w-3.5 h-3.5" />
                              )}
                              <span>VIEW / PRINT</span>
                            </button>

                            <button
                              onClick={() => handleDownloadReport(report.id)}
                              disabled={!!isCurrentRowLoading}
                              className="inline-flex items-center space-x-1.5 px-2.5 py-1.5 rounded-md text-xs font-semibold bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 border border-slate-300 dark:border-slate-700 transition disabled:opacity-50"
                              title="Download PDF document"
                            >
                              {isCurrentRowLoading === "download" ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Download className="w-3.5 h-3.5" />
                              )}
                              <span>DOWNLOAD PDF</span>
                            </button>
                          </div>

                          {currentRowError && (
                            <span className="text-[11px] text-red-600 dark:text-red-400 font-medium">
                              {currentRowError}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* DEDICATED REPORT VIEWER & PRINT MODAL */}
      {activeReportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-2xl w-full max-w-5xl h-[90vh] flex flex-col overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-950">
              <div className="flex items-center space-x-3">
                <FileText className="w-5 h-5 text-teal-600 dark:text-teal-400" />
                <div>
                  <h2 className="text-base font-bold text-slate-900 dark:text-white">
                    Medical Report Viewer
                  </h2>
                  <p className="text-xs font-mono text-slate-500">
                    Report ID: {activeReportModal.reportId}
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={handlePrintModalReport}
                  className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-teal-600 hover:bg-teal-700 text-white shadow-sm transition"
                  title="Open native browser print dialog"
                >
                  <Printer className="w-3.5 h-3.5" />
                  <span>Print Report</span>
                </button>

                <button
                  onClick={() => handleDownloadReport(activeReportModal.reportId)}
                  className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-200 hover:bg-slate-300 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-white transition"
                  title="Download copy"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download</span>
                </button>

                <button
                  onClick={handleCloseModal}
                  className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                  title="Close viewer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body / Embedded PDF View */}
            <div className="flex-1 bg-slate-100 dark:bg-slate-950 p-2 sm:p-4">
              <iframe
                ref={iframeRef}
                src={`${activeReportModal.blobUrl}#toolbar=1&navpanes=0`}
                className="w-full h-full rounded border border-slate-300 dark:border-slate-800 bg-white"
                title={`Report ${activeReportModal.reportId}`}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
