"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Database, Play, CheckCircle2, AlertCircle, RefreshCw, Cpu, Layers } from "lucide-react";

interface DBStats {
  database_engine: string;
  table_counts: Record<string, number>;
  index_count: number;
  foreign_keys_enforced: boolean;
  connection_status: string;
}

interface QueryCatalogItem {
  key: string;
  title: string;
  concept: string;
  purpose: string;
  source_location: string;
}

interface QueryDemoResult {
  query_key: string;
  title: string;
  concept: string;
  purpose: string;
  sql: string;
  params: Record<string, any>;
  columns: string[];
  rows: Record<string, any>[];
  row_count: number;
  execution_time_ms: number;
  query_plan?: any[];
  source_location: string;
}

export default function DatabaseExplorerPage() {
  const [stats, setStats] = useState<DBStats | null>(null);
  const [queries, setQueries] = useState<QueryCatalogItem[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [activeResult, setActiveResult] = useState<QueryDemoResult | null>(null);
  const [loadingQuery, setLoadingQuery] = useState(false);
  const [loadingStats, setLoadingStats] = useState(true);

  // Transaction verification state
  const [txVerifying, setTxVerifying] = useState(false);
  const [txResult, setTxResult] = useState<any>(null);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchStatsAndCatalog();
  }, []);

  const fetchStatsAndCatalog = async () => {
    setLoadingStats(true);
    setError(null);
    try {
      const [sRes, qRes] = await Promise.allSettled([
        api.get("/api/dbms/stats"),
        api.get("/api/dbms/queries"),
      ]);

      const errors: string[] = [];

      if (sRes.status === "fulfilled") {
        setStats(sRes.value.data);
      } else {
        console.error("Failed to load DBMS stats", sRes.reason);
        errors.push("Failed to load database operational statistics");
      }

      if (qRes.status === "fulfilled") {
        setQueries(qRes.value.data);
        if (qRes.value.data.length > 0 && !selectedKey) {
          setSelectedKey(qRes.value.data[0].key);
          runQuery(qRes.value.data[0].key);
        }
      } else {
        console.error("Failed to load DBMS queries catalog", qRes.reason);
        errors.push("Failed to load predefined query catalog");
      }

      if (errors.length > 0) {
        setError(errors.join(" and "));
      }
    } catch (err: any) {
      console.error("Failed to load DBMS stats", err);
      setError("An unexpected error occurred while communicating with the database explorer.");
    } finally {
      setLoadingStats(false);
    }
  };

  const runQuery = async (key: string) => {
    setLoadingQuery(true);
    try {
      const res = await api.get(`/api/dbms/query/${key}`);
      setActiveResult(res.data);
    } catch (err: any) {
      alert("Query execution failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setLoadingQuery(false);
    }
  };

  const verifyAcidTransaction = async () => {
    setTxVerifying(true);
    try {
      const res = await api.post("/api/dbms/verify-transaction");
      setTxResult(res.data);
      // Refresh stats to demonstrate non-leaked records
      fetchStatsAndCatalog();
    } catch (err: any) {
      alert("Transaction verification error: " + (err.response?.data?.detail || err.message));
    } finally {
      setTxVerifying(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 pb-5 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-teal-700 dark:text-teal-400">Core Computer Science & DBMS</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-950 dark:text-white">
            Relational Database Explorer & Query Demonstration
          </h1>
          <p className="mt-1 text-sm text-slate-500 max-w-3xl">
            Live execution of relational queries, aggregate metrics, schema normalisation proof, and ACID transaction verification against the live MediScanX database.
          </p>
        </div>
        <button
          onClick={fetchStatsAndCatalog}
          className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Refresh Live Metrics
        </button>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 p-4 border border-red-200 dark:bg-red-950/40 dark:border-red-900/50">
          <div className="text-sm text-red-700 dark:text-red-400">
            <span className="font-semibold">Notice:</span> {error}. Please verify server authentication or connectivity.
          </div>
        </div>
      )}

      {/* Live Operational Database Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">Engine Dialect</span>
          <p className="mt-1 text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Database className="h-5 w-5 text-teal-600" />
            {stats?.database_engine || "SQLITE3"}
          </p>
          <span className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 block font-medium">
            {stats?.connection_status || "Active Connection"}
          </span>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">Relational Tables</span>
          <p className="mt-1 text-xl font-bold text-slate-900 dark:text-white">
            {stats ? Object.keys(stats.table_counts).length : 12} Tables
          </p>
          <span className="text-xs text-slate-500 mt-1 block">3rd Normal Form (3NF)</span>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">Indexed Columns</span>
          <p className="mt-1 text-xl font-bold text-slate-900 dark:text-white">
            {stats?.index_count || 8} Active Indexes
          </p>
          <span className="text-xs text-slate-500 mt-1 block">B-Tree Primary & Foreign Keys</span>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">Total Recorded Tuples</span>
          <p className="mt-1 text-xl font-bold text-slate-900 dark:text-white">
            {stats ? Object.values(stats.table_counts).reduce((a, b) => a + b, 0) : 0} Rows
          </p>
          <span className="text-xs text-slate-500 mt-1 block">Authoritative Live Counts</span>
        </div>
      </div>

      {/* Table Tuple Counts Breakdown */}
      {stats && (
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
            Authoritative Schema Tuple Cardinality (Live count(*) Results)
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3">
            {Object.entries(stats.table_counts).map(([table, count]) => (
              <div key={table} className="p-2.5 rounded bg-slate-50 dark:bg-slate-950 border border-slate-100 dark:border-slate-800/80">
                <span className="text-xs text-slate-500 font-mono block truncate">{table}</span>
                <span className="text-sm font-bold text-slate-900 dark:text-white">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Query Selector and Execution Console */}
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">Predefined Query Catalog & Execution</h2>
          <p className="text-xs text-slate-500">Select an educational SQL query demonstrate core relational principles.</p>
        </div>

        <div className="flex flex-wrap gap-2">
          {queries.map((q) => (
            <button
              key={q.key}
              onClick={() => {
                setSelectedKey(q.key);
                runQuery(q.key);
              }}
              className={`px-3.5 py-2 rounded-md text-xs font-medium transition-all ${
                selectedKey === q.key
                  ? "bg-teal-700 text-white shadow-sm"
                  : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 dark:bg-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {q.title.split("(")[0]}
            </button>
          ))}
        </div>

        {/* Query Output Container */}
        {loadingQuery ? (
          <div className="flex h-64 items-center justify-center rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-700"></div>
          </div>
        ) : activeResult && (
          <div className="rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 overflow-hidden shadow-sm space-y-4 p-5">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-4">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-teal-700 dark:text-teal-400">
                  Concept: {activeResult.concept}
                </span>
                <h3 className="text-base font-bold text-slate-950 dark:text-white mt-0.5">{activeResult.title}</h3>
                <p className="text-xs text-slate-500 mt-1">{activeResult.purpose}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                  {activeResult.execution_time_ms.toFixed(2)} ms
                </span>
                <span className="text-xs font-mono px-2.5 py-1 rounded bg-teal-50 dark:bg-teal-950/40 text-teal-800 dark:text-teal-300">
                  {activeResult.row_count} rows returned
                </span>
              </div>
            </div>

            {/* SQL Query Display */}
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <span className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Executed SQL Statement</span>
                <span className="text-xs font-mono text-slate-400">{activeResult.source_location}</span>
              </div>
              <pre className="p-3.5 rounded bg-slate-950 text-slate-100 font-mono text-xs overflow-x-auto leading-relaxed border border-slate-800">
                {activeResult.sql}
              </pre>
            </div>

            {/* EXPLAIN QUERY PLAN Display if present */}
            {activeResult.query_plan && activeResult.query_plan.length > 0 && (
              <div className="bg-slate-50 dark:bg-slate-950/60 p-3 rounded border border-slate-200 dark:border-slate-800">
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1">
                  Database Optimizer Query Plan (EXPLAIN QUERY PLAN)
                </span>
                <div className="text-xs font-mono text-slate-600 dark:text-slate-400 space-y-1">
                  {activeResult.query_plan.map((step, idx) => (
                    <div key={idx}>
                      ▶ {step.detail || JSON.stringify(step)}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Table Results */}
            <div className="overflow-x-auto border-t border-slate-100 dark:border-slate-800 pt-3">
              <span className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider block mb-2">Live Query Results</span>
              {activeResult.rows.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500">
                  Query returned 0 rows for the current filter parameters.
                </div>
              ) : (
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
                    <tr>
                      {activeResult.columns.map((col) => (
                        <th key={col} className="px-3 py-2.5 font-semibold text-slate-700 dark:text-slate-300 font-mono">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                    {activeResult.rows.map((row, rIdx) => (
                      <tr key={rIdx} className="hover:bg-slate-50 dark:hover:bg-slate-800/30">
                        {activeResult.columns.map((col) => (
                          <td key={col} className="px-3 py-2 text-slate-700 dark:text-slate-300 font-mono max-w-xs truncate">
                            {row[col] !== null && row[col] !== undefined ? String(row[col]) : <span className="text-slate-400 italic">NULL</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ACID Transaction & Rollback Demonstration */}
      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 space-y-4">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-teal-700 dark:text-teal-400">ACID Properties Demonstration</span>
            <h3 className="text-lg font-bold text-slate-950 dark:text-white mt-0.5">Transaction Atomicity & Rollback Verification</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-2xl">
              Initiates an isolated database transaction, stages a test patient entity, intentionally triggers a constraint violation exception, and verifies that the transaction cleanly rolls back without leaking orphaned rows.
            </p>
          </div>
          <button
            onClick={verifyAcidTransaction}
            disabled={txVerifying}
            className="rounded-md bg-slate-900 px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-teal-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
          >
            {txVerifying ? "Executing Transaction..." : "Trigger Transaction & Verify Rollback"}
          </button>
        </div>

        {txResult && (
          <div className="mt-4 p-4 rounded-md border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950 space-y-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              <span className="text-xs font-bold text-slate-900 dark:text-white">
                {txResult.acid_property_demonstrated}: Rollback Verified = {txResult.rollback_verified ? "SUCCESS" : "FAILED"}
              </span>
            </div>

            <div className="space-y-1 font-mono text-xs text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-900 p-3 rounded border border-slate-200 dark:border-slate-800">
              {txResult.audit_trace.map((step: string, i: number) => (
                <div key={i}>{step}</div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
