"use client";

import { useEffect, useState } from "react";
import { api, CaseResponse, PatientResponse } from "@/lib/api";
import { Plus, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { formatDate } from "@/lib/utils";
import { useRouter } from "next/navigation";
import axios from "axios";

export default function CasesPage() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseResponse[]>([]);
  const [patients, setPatients] = useState<PatientResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  
  // New case modal
  const [showModal, setShowModal] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState("");
  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [cRes, pRes] = await Promise.all([
        api.get("/api/cases"),
        api.get("/api/patients"),
      ]);
      setCases(cRes.data);
      setPatients(pRes.data);
      if (pRes.data.length > 0) {
        setSelectedPatientId(pRes.data[0].id);
      }
    } catch (err) {
      console.error("Failed to load cases", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError("");
    setIsCreating(true);

    try {
      const res = await api.post("/api/cases", {
        patient_id: selectedPatientId,
        name: newName,
      });
      router.push(`/cases/${res.data.id}`);
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
      setCreateError(detail || "Failed to create case");
      setIsCreating(false);
    }
  };

  const getPatientCode = (id: string) => {
    const p = patients.find(p => p.id === id);
    return p ? p.anon_code : id.slice(0, 8);
  };

  const filteredCases = cases.filter(c => 
    c.id.toLowerCase().includes(search.toLowerCase()) ||
    getPatientCode(c.patient_id).toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">Active Cases</h1>
        </div>
        <button 
          onClick={() => setShowModal(true)}
          className="flex items-center space-x-2 bg-slate-900 dark:bg-white text-white dark:text-slate-900 px-4 py-2 rounded-lg font-medium transition-colors hover:bg-slate-800 dark:hover:bg-slate-100"
        >
          <Plus className="h-4 w-4" />
          <span>New Case</span>
        </button>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center bg-slate-50 dark:bg-slate-950">
          <div className="relative w-full max-w-md">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-4 w-4 text-slate-400" />
            </div>
            <input
              type="text"
              placeholder="Search by Case ID or Patient Code..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 w-full px-4 py-2 text-sm border border-slate-300 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-slate-400 focus:border-slate-400 bg-white dark:bg-slate-900 text-slate-900 dark:text-white transition-all outline-none"
            />
          </div>
        </div>

        {isLoading ? (
          <div className="p-20 flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900 dark:border-white"></div>
          </div>
        ) : filteredCases.length === 0 ? (
          <div className="p-16 text-center text-slate-500">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">No cases found</h3>
            <p className="text-sm mb-6 max-w-sm mx-auto">Create a new case for a registered patient to begin.</p>
            <button 
              onClick={() => setShowModal(true)}
              className="inline-flex items-center space-x-2 bg-slate-100 text-slate-900 hover:bg-slate-200 dark:bg-slate-800 dark:text-white dark:hover:bg-slate-700 font-medium px-4 py-2 rounded-md transition-colors text-sm"
            >
              <Plus className="h-4 w-4" />
              <span>Create New Case</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs font-medium text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950 uppercase border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-6 py-4">Case ID</th>
                  <th className="px-6 py-4">Case Name</th>
                  <th className="px-6 py-4">Patient Code</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">Created At</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {filteredCases.map((c) => {
                  const patient = patients.find(p => p.id === c.patient_id);
                  return (
                    <tr key={c.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                      <td className="px-6 py-4 font-mono font-medium text-slate-900 dark:text-white">
                        {c.id.substring(0, 8)}
                      </td>
                      <td className="px-6 py-4 font-bold text-slate-900 dark:text-white">
                        {c.name || "Name not recorded"}
                      </td>
                      <td className="px-6 py-4 font-bold text-slate-900 dark:text-white">
                        {patient ? patient.full_name || patient.anon_code : "Unknown"}
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium border ${
                          c.status === "completed" ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800/50" :
                          c.status === "error" ? "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800/50" :
                          "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-900/20 dark:text-slate-400 dark:border-slate-800/50"
                        }`}>
                          {c.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-slate-500 text-xs font-medium">{formatDate(c.created_at)}</td>
                      <td className="px-6 py-4 text-right space-x-4">
                        <Link href={`/cases/${c.id}`} className="text-sm font-medium text-slate-900 dark:text-white hover:underline">
                          View
                        </Link>
                        <button
                          type="button"
                          onClick={async () => {
                            if (!window.confirm("Delete this case and its uploaded data, analysis, and reports? This action is permanent.")) return;
                            try {
                              await api.delete(`/api/cases/${c.id}`);
                              setCases((current) => current.filter((item) => item.id !== c.id));
                            } catch (err: any) {
                              setCreateError(err.response?.data?.detail || "Case deletion failed.");
                            }
                          }}
                          className="inline-flex items-center gap-1 text-sm font-medium text-red-700 dark:text-red-400 hover:underline"
                          aria-label={`Delete ${c.name || c.id}`}
                        >
                          <Trash2 className="h-4 w-4" />
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 dark:bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-slate-900 rounded-lg shadow-xl w-full max-w-md border border-slate-200 dark:border-slate-800 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                New Case
              </h2>
            </div>
            
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              {createError && (
                <div className="p-3 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/10 rounded-md border border-red-100 dark:border-red-900/30">
                  {createError}
                </div>
              )}
              
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  Select Patient *
                </label>
                {patients.length === 0 ? (
                  <div className="p-3 bg-amber-50 dark:bg-amber-900/10 rounded-md border border-amber-200 dark:border-amber-800/50 text-sm text-amber-700 dark:text-amber-400">
                    <p className="font-medium mb-1">No patients available.</p>
                    <Link href="/patients" className="underline hover:text-amber-800 dark:hover:text-amber-300">Go to Patients</Link>
                  </div>
                ) : (
                  <select
                    required
                    value={selectedPatientId}
                    onChange={e => setSelectedPatientId(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-slate-400 focus:border-slate-400 bg-white dark:bg-slate-950 text-slate-900 dark:text-white transition-all outline-none"
                  >
                    <option value="" disabled>Select a patient...</option>
                    {patients.map(p => (
                      <option key={p.id} value={p.id}>
                        {p.full_name || p.anon_code} {p.age ? `(Age: ${p.age})` : ""}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  Case Name *
                </label>
                <input
                  type="text"
                  required
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-slate-400 focus:border-slate-400 bg-white dark:bg-slate-950 text-slate-900 dark:text-white transition-all outline-none"
                  placeholder="e.g. Initial Assessment"
                />
              </div>
              
              <div className="pt-4 flex justify-end space-x-3 mt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-md text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreating || patients.length === 0}
                  className="px-4 py-2 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-md text-sm font-medium disabled:opacity-50 transition-colors"
                >
                  {isCreating ? "Creating..." : "Create Case"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
