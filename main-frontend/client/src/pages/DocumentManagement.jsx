import React, { useState, useMemo, useEffect, useCallback, useRef, useLayoutEffect } from "react";
import { useLocation } from "react-router-dom";
import {
  Search,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  MoreVertical,
  HardDrive,
  FileText,
  Trash2,
  RefreshCw,
  X,
  CheckCircle,
  Clock,
  AlertCircle,
  Library,
  History,
  Database,
} from "lucide-react";
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  reprocessDocument,
  fetchDocumentsHealth,
} from "../services/documentService";
import { useAuth } from "../contexts/AuthContext";
import { API_BASE } from "../services/api";
import PortalMenu from "../components/common/PortalMenu";

/** Per-row action menu rendered via PortalMenu so it isn't clipped by the table card. */
function DocActionMenu({ open, onToggle, onClose, onReprocess, onDelete }) {
  const triggerRef = useRef(null);
  return (
    <>
      <button
        ref={triggerRef}
        onClick={onToggle}
        className="p-1 text-gray-400 hover:text-gray-700 dark:hover:text-white transition-all duration-200"
        aria-label="Actions"
      >
        <MoreVertical size={14} />
      </button>
      <PortalMenu open={open} anchorRef={triggerRef} onClose={onClose} width={172}>
        <button
          onClick={() => { onReprocess(); onClose(); }}
          className="w-full text-left flex items-center gap-2 px-3.5 py-2 text-[12.5px] text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
        >
          <RefreshCw size={12} /> Reprocess KB
        </button>
        <button
          onClick={() => { onDelete(); onClose(); }}
          className="w-full text-left flex items-center gap-2 px-3.5 py-2 text-[12.5px] text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
        >
          <Trash2 size={12} /> Delete
        </button>
      </PortalMenu>
    </>
  );
}

const ITEMS_PER_PAGE = 10;

const KB_BADGE = {
  indexed:   { label: "Indexed",    cls: "bg-green-100 text-green-700",  Icon: CheckCircle },
  queued:    { label: "Processing", cls: "bg-yellow-100 text-yellow-700", Icon: Clock },
  error:     { label: "Error",      cls: "bg-red-100 text-red-700",      Icon: AlertCircle },
  skipped:   { label: "Skipped",    cls: "bg-gray-100 text-gray-500",    Icon: null },
};

function KbBadge({ status }) {
  const cfg = KB_BADGE[status];
  if (!cfg) return null;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.cls}`}>
      {cfg.Icon && <cfg.Icon size={11} />}
      {cfg.label}
    </span>
  );
}

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return "—";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch {
    return iso;
  }
}

function extFromFilename(name = "") {
  const parts = name.split(".");
  return parts.length > 1 ? parts.pop().toUpperCase() : "FILE";
}

function formatRelativeDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const diffDays = Math.floor((Date.now() - d) / 86400000);
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return "—"; }
}

function extColorClass(ext) {
  switch (ext) {
    case "PDF":  return { bg: "bg-red-50",    text: "text-red-500",    border: "border-red-100" };
    case "DOCX":
    case "DOC":  return { bg: "bg-blue-50",   text: "text-blue-500",   border: "border-blue-100" };
    case "XLSX":
    case "XLS":  return { bg: "bg-green-50",  text: "text-green-500",  border: "border-green-100" };
    case "PPTX":
    case "PPT":  return { bg: "bg-orange-50", text: "text-orange-500", border: "border-orange-100" };
    default:     return { bg: "bg-gray-50",   text: "text-gray-400",   border: "border-gray-100" };
  }
}

// ── Animated sliding-pill tab toggle ─────────────────────────────────────────
function DocTabToggle({ activeTab, onSelect, tabRefs, indicator, setIndicator, isAdmin, indexedCount }) {
  const tabs = useMemo(() => {
    const base = [
      { key: "list",    label: "Document List" },
      { key: "upload",  label: "Upload Documents" },
      { key: "history", label: "History",          icon: History },
      { key: "indexed", label: "Indexed",          icon: Database },
    ];
    if (isAdmin) base.push({ key: "library", label: "Knowledge Library", icon: Library });
    return base;
  }, [isAdmin]);

  // Measure active tab and slide indicator (re-runs when active tab or list changes)
  useLayoutEffect(() => {
    const el = tabRefs.current[activeTab];
    if (el) {
      setIndicator({ left: el.offsetLeft, width: el.offsetWidth, ready: true });
    }
  }, [activeTab, tabs, tabRefs, setIndicator]);

  return (
    <div className="relative inline-flex bg-white rounded-full p-1 border border-gray-100 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      {/* Sliding black indicator */}
      <div
        className="absolute top-1 bottom-1 rounded-full bg-[#1f1f1f] transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
        style={{
          left: indicator.left,
          width: indicator.width,
          opacity: indicator.ready ? 1 : 0,
        }}
      />

      {tabs.map((t) => {
        const TabIcon = t.icon;
        const active = activeTab === t.key;
        return (
          <button
            key={t.key}
            ref={(el) => { tabRefs.current[t.key] = el; }}
            onClick={() => onSelect(t.key)}
            className={`relative z-10 flex items-center gap-1.5 px-4 py-1.5 text-[12px] font-medium rounded-full transition-colors duration-300 cursor-pointer ${
              active ? "text-[#FFDE39]" : "text-[#1f1f1f] hover:text-gray-700"
            }`}
          >
            {TabIcon && <TabIcon size={12} />}
            <span>{t.label}</span>
            {t.key === "indexed" && indexedCount > 0 && (
              <span className={`ml-0.5 px-1.5 py-0.5 rounded-full text-[9.5px] font-semibold leading-none transition-colors duration-300 ${
                active ? "bg-[#FFDE39]/25 text-[#FFDE39]" : "bg-green-100 text-green-700"
              }`}>
                {indexedCount}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

const DocumentManagement = () => {
  const { user } = useAuth();
  const location = useLocation();
  const isAdmin = user?.is_admin || user?.username === "admin";
  const [activeTab, setActiveTab] = useState(
    location.pathname === "/documents/upload" ? "upload" : "list"
  );

  // List tab state
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [orderFilter, setOrderFilter] = useState("All");
  const [currentPage, setCurrentPage] = useState(1);

  // Storage health
  const [storageUsed, setStorageUsed] = useState(null);

  // Action menu
  const [menuOpenId, setMenuOpenId] = useState(null);
  const menuRef = useRef(null);

  // Toggle tab pill — animated indicator
  const tabRefs = useRef({});
  const [indicator, setIndicator] = useState({ left: 0, width: 0, ready: false });

  // Upload tab state
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]);

  // Library (admin) tab state
  const [libraryDocs, setLibraryDocs] = useState([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState(null);
  const [librarySearch, setLibrarySearch] = useState("");
  const [libraryTypeFilter, setLibraryTypeFilter] = useState("All");

  // Indexed KB tab state
  const [indexedDocs, setIndexedDocs] = useState([]);
  const [indexedLoading, setIndexedLoading] = useState(false);
  const [indexedError, setIndexedError] = useState(null);

  // ---- Fetch documents ----
  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const data = await listDocuments({ page: currentPage, pageSize: ITEMS_PER_PAGE });
      if (Array.isArray(data)) {
        setDocuments(data);
        setTotalCount(data.length);
      } else {
        setDocuments(data.documents ?? []);
        setTotalCount(data.total ?? 0);
      }
    } catch (err) {
      setListError(err.message || "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, [currentPage]);

  const fetchHealth = useCallback(async () => {
    try {
      const h = await fetchDocumentsHealth();
      if (h?.storage) setStorageUsed(h.storage);
    } catch {
      // non-critical
    }
  }, []);

  const fetchLibrary = useCallback(async () => {
    if (!isAdmin) return;
    setLibraryLoading(true);
    setLibraryError(null);
    try {
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${API_BASE}/api/admin/itinerary-files`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setLibraryDocs(data.documents ?? []);
    } catch (err) {
      setLibraryError(err.message || "Failed to load library.");
    } finally {
      setLibraryLoading(false);
    }
  }, [isAdmin]);

  const fetchIndexedDocs = useCallback(async () => {
    setIndexedLoading(true);
    setIndexedError(null);
    try {
      const data = await listDocuments({ kbOnly: true, pageSize: 100 });
      const docs = Array.isArray(data) ? data : (data.documents ?? []);
      setIndexedDocs(docs);
    } catch (err) {
      setIndexedError(err.message || "Failed to load indexed documents.");
    } finally {
      setIndexedLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocs();
    fetchHealth();
  }, [fetchDocs, fetchHealth]);

  useEffect(() => {
    if (activeTab === "library") fetchLibrary();
    if (activeTab === "indexed") fetchIndexedDocs();
  }, [activeTab, fetchLibrary, fetchIndexedDocs]);

  // Close menu on outside click
  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpenId(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (activeTab === "list") fetchDocs();
  }, [activeTab, fetchDocs]);

  // ---- Client-side filter/sort ----
  const filtered = useMemo(() => {
    let result = [...documents];
    if (searchQuery.trim()) {
      result = result.filter((d) =>
        (d.filename || d.name || "").toLowerCase().includes(searchQuery.toLowerCase())
      );
    }
    if (statusFilter !== "All") {
      result = result.filter((d) => {
        const ext = extFromFilename(d.filename || d.name || "");
        return ext === statusFilter.toUpperCase();
      });
    }
    if (orderFilter === "Newest") {
      result = result.slice().sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
    } else if (orderFilter === "Oldest") {
      result = result.slice().sort((a, b) => new Date(a.uploaded_at) - new Date(b.uploaded_at));
    }
    return result;
  }, [documents, searchQuery, statusFilter, orderFilter]);

  const filteredLibrary = useMemo(() => {
    let result = [...libraryDocs];
    if (librarySearch.trim()) {
      result = result.filter((d) =>
        d.filename.toLowerCase().includes(librarySearch.toLowerCase())
      );
    }
    if (libraryTypeFilter !== "All") {
      result = result.filter((d) => extFromFilename(d.filename) === libraryTypeFilter.toUpperCase());
    }
    return result;
  }, [libraryDocs, librarySearch, libraryTypeFilter]);

  const totalPages = Math.max(1, Math.ceil((totalCount || filtered.length) / ITEMS_PER_PAGE));

  const goToPage = (page) => {
    if (page >= 1 && page <= totalPages) setCurrentPage(page);
  };

  const handleSearchChange = (val) => {
    setSearchQuery(val);
    setCurrentPage(1);
  };

  // ---- Delete ----
  const handleDelete = async (docId) => {
    setMenuOpenId(null);
    if (!window.confirm("Delete this document? This cannot be undone.")) return;
    try {
      await deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => (d.doc_id ?? d.id) !== docId));
      setTotalCount((c) => Math.max(0, c - 1));
    } catch (err) {
      alert("Delete failed: " + (err.message || "Unknown error"));
    }
  };

  // ---- Reprocess ----
  const handleReprocess = async (docId) => {
    setMenuOpenId(null);
    try {
      await reprocessDocument(docId);
      setDocuments((prev) =>
        prev.map((d) =>
          (d.doc_id ?? d.id) === docId ? { ...d, kb_status: "queued" } : d
        )
      );
    } catch (err) {
      alert("Reprocess failed: " + (err.message || "Unknown error"));
    }
  };

  // ---- Upload ----
  const addFiles = async (files) => {
    const entries = files.map((f, i) => ({
      id: Date.now() + i,
      file: f,
      name: f.name,
      size: formatSize(f.size),
      type: extFromFilename(f.name),
      progress: 0,
      status: "uploading",
      kbStatus: null,
      timeAgo: "just now",
      docId: null,
      error: null,
    }));
    setUploadedFiles((prev) => [...entries, ...prev]);

    for (const entry of entries) {
      try {
        const result = await uploadDocument(
          entry.file,
          "",
          true,
          (pct) => {
            setUploadedFiles((prev) =>
              prev.map((f) => (f.id === entry.id ? { ...f, progress: pct } : f))
            );
          }
        );
        setUploadedFiles((prev) =>
          prev.map((f) =>
            f.id === entry.id
              ? {
                  ...f,
                  status: "done",
                  progress: 100,
                  kbStatus: result.document?.kb_status ?? result.kb_status ?? "queued",
                  docId: result.document?.doc_id ?? result.doc_id ?? result.id ?? null,
                }
              : f
          )
        );
      } catch (err) {
        setUploadedFiles((prev) =>
          prev.map((f) =>
            f.id === entry.id
              ? { ...f, status: "error", error: err.message || "Upload failed" }
              : f
          )
        );
      }
    }
  };

  const handleFileDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    addFiles(Array.from(e.dataTransfer.files));
  };

  const handleFileSelect = (e) => {
    addFiles(Array.from(e.target.files));
    e.target.value = "";
  };

  const removeUploadEntry = (id) =>
    setUploadedFiles((prev) => prev.filter((f) => f.id !== id));

  // ---- Pagination buttons ----
  const renderPageNumbers = () => {
    const pages = [];
    for (let i = 1; i <= totalPages; i++) {
      pages.push(
        <button
          key={i}
          onClick={() => goToPage(i)}
          className={`w-7 h-7 rounded-lg text-xs font-medium transition-all duration-300 ${
            i === currentPage
              ? "bg-[#FFDE39] text-dark-300"
              : "text-gray-400 hover:bg-gray-100"
          }`}
        >
          {i}
        </button>
      );
    }
    return pages;
  };

  const storageLabel = storageUsed
    ? `${storageUsed.used_mb?.toFixed(1) ?? "?"} MB / ${storageUsed.total_mb?.toFixed(0) ?? "?"} MB`
    : "Storage Usage";

  return (
    <div className="animate-fadeIn">
      {/* Tab toggle (sliding pill) + storage */}
      <div className="flex items-center justify-between mb-5">
        <DocTabToggle
          activeTab={activeTab}
          onSelect={setActiveTab}
          tabRefs={tabRefs}
          indicator={indicator}
          setIndicator={setIndicator}
          isAdmin={isAdmin}
          indexedCount={indexedDocs.length}
        />

        <div className="flex items-center gap-2 bg-white border border-gray-100 rounded-md px-3 py-1.5 text-[12px]">
          <HardDrive size={13} className="text-gray-500" />
          <span className="text-gray-500">Storage Usage</span>
          <span className="font-semibold text-[#1f1f1f]">{storageLabel}</span>
        </div>
      </div>

      {/* ==================== */}
      {/* DOCUMENT LIST TAB    */}
      {/* ==================== */}
      {activeTab === "list" && (
        <div className="animate-fadeIn">
          {/* Single white card containing controls + table */}
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden shadow-[0_1px_4px_rgba(0,0,0,0.03)]">
            {/* Filters / controls row */}
            <div className="flex flex-wrap items-center gap-3 px-4 py-3">
              <h2 className="text-[15px] font-semibold text-gray-800 mr-1">Documents list</h2>

              <div className="flex items-center bg-white border border-gray-200 rounded-full px-3.5 py-1.5 w-64 focus-within:border-gray-300 transition-all duration-300">
                <Search size={14} className="text-gray-400 mr-2" />
                <input
                  type="text"
                  placeholder="Search history"
                  value={searchQuery}
                  onChange={(e) => handleSearchChange(e.target.value)}
                  className="bg-transparent outline-none text-[12.5px] text-gray-700 placeholder-gray-400 w-full font-poppins"
                />
              </div>

              <div className="flex items-center gap-2">
                <span className="text-[12.5px] text-gray-500">Status</span>
                <div className="relative">
                  <select
                    value={statusFilter}
                    onChange={(e) => { setStatusFilter(e.target.value); setCurrentPage(1); }}
                    className="appearance-none bg-white border border-gray-200 rounded-md pl-3 pr-7 py-1.5 text-[12.5px] text-gray-700 outline-none focus:border-gray-300 transition-all duration-300 cursor-pointer font-poppins min-w-[88px]"
                  >
                    <option>All</option>
                    <option>PDF</option>
                    <option>DOCX</option>
                    <option>XLSX</option>
                    <option>JPG</option>
                    <option>PNG</option>
                  </select>
                  <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-[12.5px] text-gray-500">Order</span>
                <div className="relative">
                  <select
                    value={orderFilter}
                    onChange={(e) => { setOrderFilter(e.target.value); setCurrentPage(1); }}
                    className="appearance-none bg-white border border-gray-200 rounded-md pl-3 pr-7 py-1.5 text-[12.5px] text-gray-700 outline-none focus:border-gray-300 transition-all duration-300 cursor-pointer font-poppins min-w-[88px]"
                  >
                    <option>All</option>
                    <option>Newest</option>
                    <option>Oldest</option>
                  </select>
                  <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
                </div>
              </div>

              <button
                onClick={fetchDocs}
                className="ml-auto p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-50 rounded-md transition-all duration-200"
                title="Refresh"
              >
                <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
              </button>
            </div>

            {listError && (
              <div className="mx-4 mb-3 px-4 py-2.5 bg-red-50 border border-red-100 rounded-lg text-[12px] text-red-600">
                {listError}
              </div>
            )}

            {/* Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <thead>
                  <tr className="bg-[#1f1f1f]">
                    <th className="text-left px-5 py-3 font-medium text-white">Name</th>
                    <th className="text-left px-5 py-3 font-medium text-white">Type</th>
                    <th className="text-left px-5 py-3 font-medium text-white">Size</th>
                    <th className="text-left px-5 py-3 font-medium text-white">Uploaded on</th>
                    <th className="text-left px-5 py-3 font-medium text-white">Status</th>
                    <th className="text-left px-5 py-3 font-medium text-white">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && documents.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-5 py-10 text-center text-gray-400 text-[12.5px]">
                        Loading documents…
                      </td>
                    </tr>
                  ) : filtered.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-5 py-10 text-center text-gray-400 text-[12.5px]">
                        No documents found.
                      </td>
                    </tr>
                  ) : (
                    filtered.map((doc, i) => {
                      const docId = doc.doc_id ?? doc.id;
                      const name = doc.filename ?? doc.name ?? "—";
                      const ext = extFromFilename(name);
                      return (
                        <tr
                          key={docId}
                          className={`${i % 2 === 0 ? "bg-white" : "bg-[#f5f5f5]"} hover:bg-[#FFFCE6] transition-all duration-300`}
                        >
                          <td className="px-5 py-3 text-[#1f1f1f] font-medium whitespace-nowrap max-w-[280px]">
                            <span className="block truncate underline underline-offset-2 decoration-[#1f1f1f]/60">{name}</span>
                          </td>
                          <td className="px-5 py-3 text-gray-600 whitespace-nowrap">{ext}</td>
                          <td className="px-5 py-3 text-gray-600 whitespace-nowrap">{formatSize(doc.size_bytes ?? doc.file_size ?? doc.size)}</td>
                          <td className="px-5 py-3 text-gray-600 whitespace-nowrap">{formatDate(doc.uploaded_at)}</td>
                          <td className="px-5 py-3 whitespace-nowrap">
                            <KbBadge status={doc.kb_status} />
                          </td>
                          <td className="px-5 py-3 whitespace-nowrap">
                            <DocActionMenu
                              open={menuOpenId === docId}
                              onToggle={() => setMenuOpenId(menuOpenId === docId ? null : docId)}
                              onClose={() => setMenuOpenId(null)}
                              onReprocess={() => handleReprocess(docId)}
                              onDelete={() => handleDelete(docId)}
                            />
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-end gap-1 mt-4">
              <button
                onClick={() => goToPage(currentPage - 1)}
                disabled={currentPage === 1}
                className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-300"
              >
                <ChevronLeft size={14} />
              </button>
              {renderPageNumbers()}
              <button
                onClick={() => goToPage(currentPage + 1)}
                disabled={currentPage === totalPages}
                className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-300"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}

      {/* ==================== */}
      {/* UPLOAD DOCUMENTS TAB */}
      {/* ==================== */}
      {activeTab === "upload" && (
        <div className="animate-fadeIn">
          {/* Drop zone — dashed border, yellow folder, file type chips */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleFileDrop}
            className={`bg-white rounded-xl py-12 px-6 text-center transition-all duration-300 border-2 border-dashed ${
              dragOver ? "border-[#FFDE39] bg-[#FFFCE6]/40" : "border-gray-200"
            }`}
          >
            <div className="mx-auto mb-4 w-14 h-12 flex items-center justify-center">
              <svg width="56" height="48" viewBox="0 0 56 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M4 8C4 5.79 5.79 4 8 4H20L26 10H48C50.21 10 52 11.79 52 14V40C52 42.21 50.21 44 48 44H8C5.79 44 4 42.21 4 40V8Z" fill="#FFDE39" stroke="#E6C800" strokeWidth="1.5"/>
                <path d="M28 20V32M22 26L28 20L34 26" stroke="#1f1f1f" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <p className="text-[13px] text-gray-600">
              Drag &amp; Drop or{" "}
              <label className="font-medium text-[#1f1f1f] bg-[#FFDE39] hover:bg-[#FFEC85] cursor-pointer transition-colors duration-200 px-1.5 py-0.5 rounded">
                Choose File
                <input type="file" multiple onChange={handleFileSelect} className="hidden" />
              </label>{" "}
              to upload here
            </p>
            <div className="flex items-center justify-center flex-wrap gap-1.5 mt-3">
              {["PDF", "DocX", "Xlsx", "JPG", "PNG", "ZIP"].map((fmt) => (
                <span
                  key={fmt}
                  className="text-[10px] text-gray-500 border border-gray-200 px-2 py-0.5 rounded font-medium"
                >
                  {fmt}
                </span>
              ))}
            </div>
          </div>

          {uploadedFiles.length > 0 && (
            <div className="mt-6">
              <h3 className="text-[14px] font-semibold text-gray-800 mb-3">Uploaded Files</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {uploadedFiles.map((file) => (
                  <div
                    key={file.id}
                    className="flex items-center gap-3 bg-white rounded-lg border border-gray-100 shadow-[0_1px_3px_rgba(0,0,0,0.03)] px-3 py-2.5 transition-all duration-300 hover:shadow-[0_3px_10px_rgba(0,0,0,0.05)]"
                  >
                    <div className="w-9 h-9 rounded-md bg-gray-50 border border-gray-100 flex items-center justify-center flex-shrink-0">
                      <FileText size={15} className="text-[#1f1f1f]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[12.5px] font-semibold text-[#1f1f1f] truncate">{file.name}</p>
                      <p className="text-[11px] text-gray-400 mt-0.5">{file.size} · {file.type}</p>
                      {file.status === "uploading" && (
                        <div className="mt-1.5 h-1 w-full bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[#FFDE39] rounded-full transition-all duration-300"
                            style={{ width: `${file.progress}%` }}
                          />
                        </div>
                      )}
                      {file.status === "done" && file.kbStatus && (
                        <div className="mt-1"><KbBadge status={file.kbStatus} /></div>
                      )}
                      {file.status === "error" && (
                        <p className="mt-1 text-[11px] text-red-500 truncate">{file.error}</p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <span className="text-[11px] text-gray-400 whitespace-nowrap">{file.timeAgo}</span>
                      <button onClick={() => removeUploadEntry(file.id)} className="p-0.5 text-gray-300 hover:text-gray-500 transition-colors">
                        <X size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ==================== */}
      {/* HISTORY TAB          */}
      {/* ==================== */}
      {activeTab === "history" && (
        <div className="animate-fadeIn">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-sm font-semibold text-gray-800">Upload History</h2>
              <p className="text-xs text-gray-400 mt-0.5">Recently uploaded documents, newest first</p>
            </div>
            <button
              onClick={fetchDocs}
              className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-all duration-300"
              title="Refresh"
            >
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>

          {loading && documents.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw size={18} className="animate-spin text-gray-400" />
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="w-12 h-12 rounded-full bg-[#FFFAC5] border-2 border-[#FFDE39]/40 flex items-center justify-center mb-3">
                <History size={20} className="text-[#E6C800]" />
              </div>
              <p className="text-sm text-gray-500">No documents uploaded yet.</p>
              <button
                onClick={() => setActiveTab("upload")}
                className="mt-3 text-xs font-medium text-[#8A6800] bg-[#FFFAC5] hover:bg-[#FFDE39] px-3 py-1.5 rounded-full border border-[#FFDE39]/50 transition-all duration-300 cursor-pointer"
              >
                Upload a document
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {[...documents]
                .sort((a, b) => new Date(b.uploaded_at || 0) - new Date(a.uploaded_at || 0))
                .slice(0, 30)
                .map((doc) => {
                  const docId = doc.doc_id ?? doc.id;
                  const name  = doc.filename ?? doc.name ?? "—";
                  const ext   = extFromFilename(name);
                  const colors = extColorClass(ext);
                  return (
                    <div
                      key={docId}
                      className="flex items-start gap-3 bg-gradient-to-br from-[#FFFCE6]/60 to-white rounded-xl border border-[#FFDE39]/20 shadow-[0_1px_4px_rgba(255,222,57,0.06)] px-4 py-3 transition-all duration-300 hover:shadow-[0_4px_12px_rgba(255,222,57,0.14)] hover:-translate-y-0.5"
                    >
                      <div className={`w-10 h-10 rounded-lg border flex items-center justify-center flex-shrink-0 ${colors.bg} ${colors.border}`}>
                        <FileText size={18} className={colors.text} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-gray-800 truncate">{name}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${colors.bg} ${colors.text}`}>{ext}</span>
                          <span className="text-xs text-gray-400">{formatSize(doc.size_bytes ?? doc.file_size ?? doc.size)}</span>
                        </div>
                        <div className="flex items-center justify-between mt-1.5">
                          <span className="text-xs text-gray-400 flex items-center gap-1">
                            <Clock size={10} />
                            {formatRelativeDate(doc.uploaded_at)}
                          </span>
                          {doc.kb_status && <KbBadge status={doc.kb_status} />}
                        </div>
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      )}

      {/* ==================== */}
      {/* INDEXED KB TAB       */}
      {/* ==================== */}
      {activeTab === "indexed" && (
        <div className="animate-fadeIn">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-sm font-semibold text-gray-800">Indexed Documents</h2>
              <p className="text-xs text-gray-400 mt-0.5">Documents indexed into the knowledge base and used for itinerary generation</p>
            </div>
            <button
              onClick={fetchIndexedDocs}
              className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-all duration-300"
              title="Refresh"
            >
              <RefreshCw size={14} className={indexedLoading ? "animate-spin" : ""} />
            </button>
          </div>

          {indexedError && (
            <div className="mb-4 px-4 py-2.5 bg-red-50 border border-red-100 rounded-xl text-xs text-red-600">
              {indexedError}
            </div>
          )}

          {indexedLoading ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw size={18} className="animate-spin text-gray-400" />
            </div>
          ) : indexedDocs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="w-12 h-12 rounded-full bg-[#FFFAC5] border-2 border-[#FFDE39]/40 flex items-center justify-center mb-3">
                <Database size={20} className="text-[#E6C800]" />
              </div>
              <p className="text-sm text-gray-500">No indexed documents yet.</p>
              <p className="text-xs text-gray-400 mt-1">Upload pricing or hotel documents and they will appear here once processed.</p>
              <button
                onClick={() => setActiveTab("upload")}
                className="mt-3 text-xs font-medium text-[#8A6800] bg-[#FFFAC5] hover:bg-[#FFDE39] px-3 py-1.5 rounded-full border border-[#FFDE39]/50 transition-all duration-300 cursor-pointer"
              >
                Upload a document
              </button>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-100/80 overflow-hidden shadow-[0_1px_4px_rgba(0,0,0,0.04)]">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-dark-300 text-white">
                      <th className="text-left px-4 py-2.5 font-semibold">Document</th>
                      <th className="text-left px-4 py-2.5 font-semibold">Cities</th>
                      <th className="text-left px-4 py-2.5 font-semibold">Signals</th>
                      <th className="text-left px-4 py-2.5 font-semibold">Size</th>
                      <th className="text-left px-4 py-2.5 font-semibold">Indexed On</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {indexedDocs.map((doc) => {
                      const docId = doc.doc_id ?? doc.id;
                      const name  = doc.filename ?? doc.name ?? "—";
                      const ext   = extFromFilename(name);
                      const cities = doc.kb_cities ?? [];
                      return (
                        <tr key={docId} className="hover:bg-gray-50 transition-all duration-300">
                          <td className="px-4 py-3 whitespace-nowrap max-w-xs">
                            <div className="flex items-center gap-2">
                              <FileText size={13} className="text-gray-400 flex-shrink-0" />
                              <span className="font-medium text-gray-800 truncate">{name}</span>
                              <span className="text-gray-400 uppercase">{ext}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-gray-600">
                            {cities.length > 0
                              ? cities.slice(0, 3).join(", ") + (cities.length > 3 ? ` +${cities.length - 3}` : "")
                              : <span className="text-gray-300">—</span>}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <div className="flex items-center gap-1.5">
                              {doc.kb_has_pricing && (
                                <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 text-[10px] font-medium">Pricing</span>
                              )}
                              {doc.kb_has_hotels && (
                                <span className="px-1.5 py-0.5 rounded bg-purple-50 text-purple-600 text-[10px] font-medium">Hotels</span>
                              )}
                              {!doc.kb_has_pricing && !doc.kb_has_hotels && (
                                <span className="text-gray-300 text-[10px]">—</span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                            {doc.kb_char_count ? `${(doc.kb_char_count / 1000).toFixed(1)}k chars` : formatSize(doc.size_bytes ?? doc.file_size ?? doc.size)}
                          </td>
                          <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                            {formatDate(doc.kb_processed_at ?? doc.uploaded_at)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="px-4 py-2.5 border-t border-gray-100 text-xs text-gray-400">
                {indexedDocs.length} indexed document{indexedDocs.length !== 1 ? "s" : ""} — used as context when generating itineraries
              </div>
            </div>
          )}
        </div>
      )}

      {/* ==================== */}
      {/* KNOWLEDGE LIBRARY    */}
      {/* ==================== */}
      {activeTab === "library" && isAdmin && (
        <div className="animate-fadeIn">
          <div className="flex flex-wrap items-center gap-3 mb-5">
            <h2 className="text-sm font-semibold text-gray-800 mr-1">Knowledge Library</h2>
            <span className="text-xs text-gray-400">— itinerary files pre-loaded as context</span>

            <div className="flex items-center bg-white border border-gray-100/80 rounded-lg px-3 py-1.5 w-52 shadow-[0_1px_4px_rgba(0,0,0,0.04)] focus-within:shadow-[0_4px_12px_rgba(0,0,0,0.06)] focus-within:border-gray-300 transition-all duration-300">
              <Search size={14} className="text-gray-400 mr-2" />
              <input
                type="text"
                placeholder="Search library"
                value={librarySearch}
                onChange={(e) => setLibrarySearch(e.target.value)}
                className="bg-transparent outline-none text-xs text-gray-700 placeholder-gray-400 w-full font-poppins"
              />
            </div>

            <div className="flex items-center gap-1.5">
              <span className="text-xs text-gray-500">Type</span>
              <div className="relative">
                <select
                  value={libraryTypeFilter}
                  onChange={(e) => setLibraryTypeFilter(e.target.value)}
                  className="appearance-none bg-white border border-gray-100/80 rounded-lg px-3 py-1.5 pr-7 text-xs text-gray-700 outline-none shadow-[0_1px_4px_rgba(0,0,0,0.04)] cursor-pointer font-poppins"
                >
                  <option>All</option>
                  <option>PDF</option>
                  <option>DOCX</option>
                  <option>XLSX</option>
                  <option>PPTX</option>
                </select>
                <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
              </div>
            </div>

            <button
              onClick={fetchLibrary}
              className="ml-auto p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-all duration-300"
              title="Refresh"
            >
              <RefreshCw size={14} className={libraryLoading ? "animate-spin" : ""} />
            </button>
          </div>

          {libraryError && (
            <div className="mb-4 px-4 py-2.5 bg-red-50 border border-red-100 rounded-xl text-xs text-red-600">
              {libraryError}
            </div>
          )}

          <div className="bg-white rounded-xl border border-gray-100/80 overflow-hidden shadow-[0_1px_4px_rgba(0,0,0,0.04)] transition-all duration-300 hover:shadow-[0_4px_12px_rgba(0,0,0,0.06)]">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-dark-300 text-white">
                    <th className="text-left px-4 py-2.5 font-semibold">Name</th>
                    <th className="text-left px-4 py-2.5 font-semibold">Type</th>
                    <th className="text-left px-4 py-2.5 font-semibold">Size</th>
                    <th className="text-left px-4 py-2.5 font-semibold">Last Modified</th>
                    <th className="text-left px-4 py-2.5 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {libraryLoading ? (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-gray-400 text-xs">
                        Loading library…
                      </td>
                    </tr>
                  ) : filteredLibrary.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-gray-400 text-xs">
                        No files found in library.
                      </td>
                    </tr>
                  ) : (
                    filteredLibrary.map((doc) => {
                      const ext = extFromFilename(doc.filename);
                      return (
                        <tr key={doc.doc_id} className="hover:bg-gray-50 transition-all duration-300">
                          <td className="px-4 py-3 text-gray-800 font-medium whitespace-nowrap max-w-xs truncate">
                            <div className="flex items-center gap-2">
                              <FileText size={14} className="text-gray-400 flex-shrink-0" />
                              {doc.filename}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{ext}</td>
                          <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{formatSize(doc.file_size)}</td>
                          <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{formatDate(doc.uploaded_at)}</td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <KbBadge status={doc.kb_status} />
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
            {filteredLibrary.length > 0 && (
              <div className="px-4 py-2.5 border-t border-gray-100 text-xs text-gray-400">
                {filteredLibrary.length} file{filteredLibrary.length !== 1 ? "s" : ""} in library
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default DocumentManagement;
