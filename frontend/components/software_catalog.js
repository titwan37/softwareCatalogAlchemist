import { useState, useEffect, useMemo } from 'react';
import { Search, FolderOpen, FileText, AlertCircle, CheckCircle2, RefreshCw, ChevronRight, ChevronDown, Trash2, MoveUp, MoveDown, Play, RotateCcw } from 'lucide-react';

const SoftwareCatalog = () => {
  const [sourcePath, setSourcePath] = useState('');
  const [scanProgress, setScanProgress] = useState(0);
  const [scanStats, setScanStats] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [catalogItems, setCatalogItems] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);
  const [treeDiff, setTreeDiff] = useState({ before: [], after: [] });
  const [isDryRun, setIsDryRun] = useState(true);

  // Simulated scan progress and stats
  useEffect(() => {
    let interval;
    if (sourcePath && !scanProgress) {
      interval = setInterval(() => {
        setScanProgress((prev) => {
          if (prev >= 100) return 100;
          return prev + Math.floor(Math.random() * 15);
        });
      }, 200);
    }
    return () => clearInterval(interval);
  }, [sourcePath, scanProgress]);

  const handleScan = () => {
    if (!sourcePath) return;
    setScanProgress(0);
    setScanStats(null);
    
    // Simulate API call delay
    setTimeout(() => {
      setScanStats({
        totalBinaries: Math.floor(Math.random() * 500) + 100,
        uniqueHashes: Math.floor(Math.random() * 300) + 50,
        duplicateSpaceWasted: (Math.random() * 2.5).toFixed(2) + ' GB',
        status: 'success'
      });
    }, 1500);
  };

  const filteredItems = useMemo(() => {
    return catalogItems.filter(item => {
      const matchesSearch = item.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          item.vendor.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === 'All' || item.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [catalogItems, searchQuery, selectedCategory]);

  const handleReorganize = () => {
    if (!isDryRun) {
      alert('Executing reorganization... (Simulation Mode: ' + isDryRun + ')');
    } else {
      console.log('Dry-run simulation started for:', treeDiff.after.length, 'items');
    }
  };

  const handleRollback = () => {
    if (!isDryRun) {
      alert('Rolling back changes...');
    } else {
      console.log('Rollback simulation started');
    }
  };

  return (
    <div className="p-6 bg-gray-50 min-h-screen font-sans text-gray-900">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* 1. Scan Control Bar */}
        <section className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
            <RefreshCw className="w-5 h-5 text-blue-600" />
            Scan Control Bar
          </h2>
          <div className="flex flex-col md:flex-row gap-4">
            <input
              type="text"
              placeholder="Enter messy repository path (e.g., /var/log/app/...)"
              className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 outline-none transition-colors"
              value={sourcePath}
              onChange={(e) => setSourcePath(e.target.value)}
            />
            <button
              onClick={handleScan}
              disabled={!sourcePath || scanProgress > 0}
              className={`px-6 py-2 rounded-md font-medium transition-colors flex items-center gap-2 ${
                !sourcePath || scanProgress > 0 
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed' 
                  : 'bg-blue-600 hover:bg-blue-700 text-white shadow-lg'
              }`}
            >
              <RefreshCw className="w-4 h-4" />
              {scanProgress > 0 ? 'Scanning...' : 'Start Scan'}
            </button>
          </div>

          {/* Progress Metrics */}
          {scanProgress > 0 && (
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-sm font-medium text-gray-600">
                <span>Scanning...</span>
                <span>{Math.round(scanProgress)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                <div 
                  className="bg-blue-600 h-2.5 rounded-full transition-all duration-300 ease-out" 
                  style={{ width: `${scanProgress}%` }}
                ></div>
              </div>
              {scanStats && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4 text-sm">
                  <div className="bg-blue-50 p-3 rounded border border-blue-100 flex items-center gap-3">
                    <FileText className="w-5 h-5 text-blue-600" />
                    <span>Total Binaries: {scanStats.totalBinaries}</span>
                  </div>
                  <div className="bg-green-50 p-3 rounded border border-green-100 flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-green-600" />
                    <span>Unique Hashes: {scanStats.uniqueHashes}</span>
                  </div>
                  <div className="bg-red-50 p-3 rounded border border-red-100 flex items-center gap-3">
                    <AlertCircle className="w-5 h-5 text-red-600" />
                    <span>Duplicate Space Wasted: {scanStats.duplicateSpaceWasted}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        {/* 2. Catalog Explorer Grid */}
        <section className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          
          {/* Sidebar Filters */}
          <aside className="lg:col-span-1 space-y-4">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
              <h3 className="font-semibold mb-3 text-gray-700 flex items-center gap-2">
                <Search className="w-4 h-4" /> Search & Filter
              </h3>
              <input
                type="text"
                placeholder="FTS5 Instant Search..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-1 focus:ring-blue-500 outline-none mb-3"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <div className="space-y-2">
                {['All', 'Utilities', 'Databases', 'Frameworks'].map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                      selectedCategory === cat 
                        ? 'bg-blue-600 text-white' 
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            {/* Metadata Inspector Modal Trigger */}
            {selectedItem && (
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
                <h3 className="font-semibold mb-3 text-gray-700 flex items-center gap-2">
                  <FileText className="w-4 h-4" /> Metadata Inspector
                </h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Vendor:</span>
                    <span className="font-medium">{selectedItem.vendor}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Architecture:</span>
                    <span className="font-medium">{selectedItem.architecture}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Confidence:</span>
                    <span className={`font-medium ${selectedItem.confidence > 0.9 ? 'text-green-600' : 'text-yellow-600'}`}>
                      {Math.round(selectedItem.confidence * 100)}%
                    </span>
                  </div>
                </div>
                <button 
                  onClick={() => setSelectedItem(null)}
                  className="mt-4 w-full py-2 text-sm text-gray-500 hover:text-gray-700 underline"
                >
                  Close Inspector
                </button>
              </div>
            )}
          </aside>

          {/* Main Grid */}
          <main className="lg:col-span-3 space-y-4">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <div className="p-4 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
                <h3 className="font-semibold text-gray-700">Software Catalog ({filteredItems.length} items)</h3>
                {selectedItem && (
                  <button 
                    onClick={() => setSelectedItem(null)}
                    className="text-sm text-blue-600 hover:underline"
                  >
                    Clear Selection
                  </button>
                )}
              </div>
              
              <div className="divide-y divide-gray-100">
                {filteredItems.map((item, idx) => (
                  <div 
                    key={idx}
                    onClick={() => setSelectedItem(item)}
                    className="p-4 hover:bg-blue-50 cursor-pointer transition-colors flex items-center justify-between group"
                  >
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-white font-bold ${
                        item.category === 'Utilities' ? 'bg-purple-500' : 
                        item.category === 'Databases' ? 'bg-blue-500' : 
                        item.category === 'Frameworks' ? 'bg-pink-500' : 'bg-gray-500'
                      }`}>
                        {item.name.charAt(0)}
                      </div>
                      <div>
                        <h4 className="font-medium text-gray-900 group-hover:text-blue-600">{item.name}</h4>
                        <p className="text-sm text-gray-500">{item.vendor} • {item.architecture}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                        item.confidence > 0.9 ? 'bg-green-100 text-green-700' : 
                        item.confidence > 0.7 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'
                      }`}>
                        {Math.round(item.confidence * 100)}%
                      </span>
                      <select 
                        className="text-sm border-gray-300 rounded-md py-1 pl-2 pr-8 focus:ring-blue-500 outline-none"
                        value={item.category}
                        onChange={(e) => {
                          const newCat = e.target.value;
                          setCatalogItems(prev => prev.map(i => 
                            i.id === item.id ? { ...i, category: newCat } : i
                          ));
                        }}
                      >
                        <option value="Utilities">Utilities</option>
                        <option value="Databases">Databases</option>
                        <option value="Frameworks">Frameworks</option>
                      </select>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </main>
        </section>

        {/* 3. Interactive Before/After Tree Diff */}
        <section className="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden">
          <div className="p-6 border-b border-gray-100 flex justify-between items-center bg-gray-50">
            <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
              <FolderOpen className="w-5 h-5" />
              Tree Diff Explorer
            </h2>
            <div className="flex gap-2">
              <button 
                onClick={handleReorganize}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors shadow-sm"
              >
                <Play className="w-4 h-4 fill-current" />
                {isDryRun ? 'Dry-Run Simulation' : 'Execute Reorganization'}
              </button>
              <button 
                onClick={handleRollback}
                className="flex items-center gap-2 px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md font-medium transition-colors shadow-sm"
              >
                <RotateCcw className="w-4 h-4 fill-current" />
                Rollback
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-200">
            
            {/* Before State */}
            <div className="p-6 bg-gray-50/50 border-r border-gray-200">
              <h3 className="font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-red-500"></span>
                Current State (Chaotic)
              </h3>
              <div className="space-y-1">
                {treeDiff.before.map((node, idx) => (
                  <div key={`before-${idx}`} className="flex items-center gap-2 text-sm text-gray-600 py-1">
                    <ChevronDown className="w-3 h-3 flex-shrink-0" />
                    <span>{node.path}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* After State */}
            <div className="p-6 bg-blue-50/30">
              <h3 className="font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-500"></span>
                Proposed Taxonomy
              </h3>
              <div className="space-y-1">
                {treeDiff.after.map((node, idx) => (
                  <div key={`after-${idx}`} className="flex items-center gap-2 text-sm text-gray-800 py-1 font-medium">
                    <ChevronDown className="w-3 h-3 flex-shrink-0" />
                    <span>{node.path}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>
        </section>

      </div>
    </div>
  );
};

export default SoftwareCatalog;
