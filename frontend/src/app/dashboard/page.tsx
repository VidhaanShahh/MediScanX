"use client";

import { useEffect, useState } from "react";
import { api, CaseResponse, PatientResponse } from "@/lib/api";
import Link from "next/link";
import { formatDate } from "@/lib/utils";
import { useRouter } from "next/navigation";

export default function DashboardPage() {
  const router = useRouter();
  const [patients, setPatients] = useState<PatientResponse[]>([]);
  const [cases, setCases] = useState<CaseResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [pRes, cRes] = await Promise.all([
          api.get("/api/patients"),
          api.get("/api/cases"),
        ]);
        setPatients(pRes.data);
        setCases(cRes.data);
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, []);

  const completedAnalyses = cases.filter((c) => c.status === "completed").length;
  const pendingCases = cases.filter((c) => c.status !== "completed").length;

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <p className="text-sm font-medium text-teal-700 dark:text-teal-400">Screening workspace</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">Dashboard</h1>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900 dark:border-white"></div>
        </div>
      ) : (
        <>
          {/* Main Stats Row */}
          <div className="grid grid-cols-2 gap-3 border-y border-slate-200 py-4 sm:grid-cols-4 dark:border-slate-800">
            <div className="px-2">
              <p className="text-xs font-medium text-slate-500">Patients</p>
              <h3 className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">{patients.length}</h3>
            </div>
            <div className="border-l border-slate-200 px-4 dark:border-slate-800">
              <p className="text-xs font-medium text-slate-500">Cases</p>
              <h3 className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">{cases.length}</h3>
            </div>
            <div className="border-l border-slate-200 px-4 dark:border-slate-800">
              <p className="text-xs font-medium text-slate-500">Completed analyses</p>
              <h3 className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">{completedAnalyses}</h3>
            </div>
            <div className="border-l border-slate-200 px-4 dark:border-slate-800">
              <p className="text-xs font-medium text-slate-500">Pending cases</p>
              <h3 className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">{pendingCases}</h3>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 pt-4">
            
            {/* Left Column: Recent Cases */}
            <div className="lg:col-span-2 space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-950 dark:text-white">Recent cases</h2>
              </div>

              <div className="overflow-hidden border-y border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950/40">
                {cases.length === 0 ? (
                  <div className="p-12 text-center text-slate-500">
                    <p className="font-medium text-slate-900 dark:text-white">No cases available</p>
                    <p className="text-sm mt-1">Create a patient and case to begin screening.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                      <thead className="border-b border-slate-200 text-xs font-medium text-slate-500 dark:border-slate-800">
                        <tr>
                          <th className="px-6 py-4">Case Name</th>
                          <th className="px-6 py-4">Patient</th>
                          <th className="px-6 py-4">Status</th>
                          <th className="px-6 py-4">Created</th>
                          <th className="px-6 py-4 text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                        {cases.slice(0, 5).map((c) => {
                          const patientInfo = patients.find(p => p.id === c.patient_id);
                          return (
                            <tr key={c.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                              <td className="px-6 py-4 font-mono text-xs text-slate-600 dark:text-slate-400">{c.name || "Name not recorded"}</td>
                              <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">
                                {patientInfo?.full_name || patientInfo?.anon_code || "Unknown"}
                              </td>
                              <td className="px-6 py-4">
                                <span className={`inline-flex px-2 py-1 rounded text-xs font-medium border ${
                                  c.status === "completed" ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800/50" :
                                  c.status === "error" ? "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800/50" :
                                  "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-900/20 dark:text-slate-400 dark:border-slate-800/50"
                                }`}>
                                  {c.status.toUpperCase()}
                                </span>
                              </td>
                              <td className="px-6 py-4 text-slate-500 text-xs font-medium">{formatDate(c.created_at)}</td>
                              <td className="px-6 py-4 text-right">
                                <Link href={`/cases/${c.id}`} className="text-slate-900 dark:text-white font-medium hover:underline">
                                  View
                                </Link>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            {/* Right Column: Actions */}
            <div className="space-y-6">
              
              <div className="border-y border-slate-200 py-5 dark:border-slate-800">
                <h2 className="mb-4 text-sm font-semibold text-slate-950 dark:text-white">
                  Start a workflow
                </h2>
                <div className="space-y-3">
                  <button 
                    onClick={() => router.push('/patients')}
                    className="w-full rounded-md border border-slate-200 px-4 py-2.5 text-left text-sm font-medium text-slate-900 transition-colors hover:border-teal-600 hover:bg-teal-50 dark:border-slate-800 dark:text-white dark:hover:bg-teal-950/30"
                  >
                    New Patient
                  </button>
                  <button 
                    onClick={() => router.push('/cases')}
                    className="w-full rounded-md border border-slate-200 px-4 py-2.5 text-left text-sm font-medium text-slate-900 transition-colors hover:border-teal-600 hover:bg-teal-50 dark:border-slate-800 dark:text-white dark:hover:bg-teal-950/30"
                  >
                    New Case
                  </button>
                </div>
              </div>

              <div className="border-y border-slate-200 py-5 dark:border-slate-800">
                <h2 className="mb-4 text-sm font-semibold text-slate-950 dark:text-white">
                  Models
                </h2>
                <div className="space-y-4">
                  <div>
                    <h4 className="text-sm font-medium text-slate-900 dark:text-white">M5 Chest X-ray</h4>
                    <p className="text-xs text-slate-500 mt-1">DenseNet121 / 14 conditions</p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-slate-900 dark:text-white">M6 ECG Analytics</h4>
                    <p className="text-xs text-slate-500 mt-1">1D-CNN / 12-lead signal</p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-slate-900 dark:text-white">M7 Decision Fusion</h4>
                    <p className="text-xs text-slate-500 mt-1">Decision-level probability fusion</p>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </>
      )}
    </div>
  );
}
