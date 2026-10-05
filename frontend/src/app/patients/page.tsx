"use client";

import { useEffect, useState } from "react";
import { api, PatientResponse, CaseResponse } from "@/lib/api";
import { Plus, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { formatDate } from "@/lib/utils";

export default function PatientsPage() {
  const [patients, setPatients] = useState<PatientResponse[]>([]);
  const [cases, setCases] = useState<CaseResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  
  // New patient modal state
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [newAge, setNewAge] = useState("");
  const [newSex, setNewSex] = useState("M");
  const [createError, setCreateError] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [pRes, cRes] = await Promise.all([
        api.get("/api/patients"),
        api.get("/api/cases"),
      ]);
      setPatients(pRes.data);
      setCases(cRes.data);
    } catch (err) {
      console.error("Failed to load patients", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError("");
    setIsCreating(true);

    try {
      await api.post("/api/patients/", {
        full_name: newName,
        age: newAge ? parseInt(newAge) : null,
        sex: newSex
      });
      setShowModal(false);
      setNewName("");
      setNewAge("");
      setNewSex("M");
      fetchData();
    } catch (err: any) {
      let errorMessage = "Failed to create patient";
      if (err.response?.data?.detail) {
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        } else if (Array.isArray(err.response.data.detail)) {
          errorMessage = err.response.data.detail.map((d: any) => d.msg).join(", ");
        }
      }
      setCreateError(errorMessage);
    } finally {
      setIsCreating(false);
    }
  };

  const filteredPatients = patients.filter(p => 
    p.anon_code.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">Patient Registry</h1>
        </div>
        <button 
          onClick={() => setShowModal(true)}
          className="flex items-center space-x-2 bg-slate-900 dark:bg-white text-white dark:text-slate-900 px-4 py-2 rounded-lg font-medium transition-colors hover:bg-slate-800 dark:hover:bg-slate-100"
        >
          <Plus className="h-4 w-4" />
          <span>Add Patient</span>
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
              placeholder="Search patients by code..."
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
        ) : filteredPatients.length === 0 ? (
          <div className="p-16 text-center text-slate-500">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">No patients found</h3>
            <p className="text-sm mb-6 max-w-sm mx-auto">Create a new anonymized patient record to begin.</p>
            <button 
              onClick={() => setShowModal(true)}
              className="inline-flex items-center space-x-2 bg-slate-100 text-slate-900 hover:bg-slate-200 dark:bg-slate-800 dark:text-white dark:hover:bg-slate-700 font-medium px-4 py-2 rounded-md transition-colors text-sm"
            >
              <Plus className="h-4 w-4" />
              <span>Add Patient</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs font-medium text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950 uppercase border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-6 py-4">Patient Name</th>
                  <th className="px-6 py-4">Anonymous ID</th>
                  <th className="px-6 py-4">Age</th>
                  <th className="px-6 py-4">Sex</th>
                  <th className="px-6 py-4">Created At</th>
                  <th className="px-6 py-4">Cases</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {filteredPatients.map((p) => {
                  const patientCases = cases.filter(c => c.patient_id === p.id);
                  return (
                    <tr key={p.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                      <td className="px-6 py-4 font-bold text-slate-900 dark:text-white">
                        {p.full_name || "Name not recorded"}
                      </td>
                      <td className="px-6 py-4 text-slate-500">
                        {p.anon_code}
                      </td>
                      <td className="px-6 py-4 text-slate-700 dark:text-slate-300">{p.age || "N/A"}</td>
                      <td className="px-6 py-4 text-slate-700 dark:text-slate-300">
                        {p.sex === 'M' ? 'Male' : p.sex === 'F' ? 'Female' : p.sex === 'O' ? 'Other' : 'N/A'}
                      </td>
                      <td className="px-6 py-4 text-slate-500 text-xs font-medium">{formatDate(p.created_at)}</td>
                      <td className="px-6 py-4">
                        <span className="text-slate-700 dark:text-slate-300 font-medium">
                          {patientCases.length}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right space-x-4">
                        <Link href={`/patients/${p.id}`} className="text-sm font-medium text-slate-900 dark:text-white hover:underline">
                          View
                        </Link>
                        <button
                          type="button"
                          onClick={async () => {
                            if (!window.confirm("Delete this patient and all associated cases and analysis data? This action is permanent.")) return;
                            try {
                              await api.delete(`/api/patients/${p.id}`);
                              setPatients((current) => current.filter((item) => item.id !== p.id));
                              setCases((current) => current.filter((item) => item.patient_id !== p.id));
                            } catch (err: any) {
                              setCreateError(err.response?.data?.detail || "Patient deletion failed.");
                            }
                          }}
                          className="inline-flex items-center gap-1 text-sm font-medium text-red-700 dark:text-red-400 hover:underline"
                          aria-label={`Delete ${p.anon_code}`}
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
            <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                Add Patient Record
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
                  Full Name *
                </label>
                <input
                  type="text"
                  required
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-slate-400 focus:border-slate-400 bg-white dark:bg-slate-950 text-slate-900 dark:text-white transition-all outline-none"
                  placeholder="e.g. John Doe"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    Age
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="150"
                    value={newAge}
                    onChange={e => setNewAge(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-slate-400 focus:border-slate-400 bg-white dark:bg-slate-950 text-slate-900 dark:text-white transition-all outline-none"
                    placeholder="Optional"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    Sex
                  </label>
                  <select
                    value={newSex}
                    onChange={e => setNewSex(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-md focus:ring-1 focus:ring-slate-400 focus:border-slate-400 bg-white dark:bg-slate-950 text-slate-900 dark:text-white transition-all outline-none"
                  >
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="O">Other</option>
                  </select>
                </div>
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
                  disabled={isCreating}
                  className="px-4 py-2 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-md text-sm font-medium disabled:opacity-50 transition-colors"
                >
                  {isCreating ? "Saving..." : "Save Patient"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
