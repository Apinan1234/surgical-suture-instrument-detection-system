import { useState } from 'react';
import { Menu, X, Eye } from 'lucide-react';

interface HeaderProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export function Header({ activeTab, setActiveTab }: HeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = ['Overview', 'Detects', 'Pipeline', 'YOLOv11', 'Results', 'Future'];

  return (
    <header className="relative z-30 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-4 sm:pt-6">
      <div className="grid grid-cols-2 md:grid-cols-3 items-center justify-between">
        {/* Brand Logo - Left */}
        <div className="flex items-center justify-start gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-white flex items-center justify-center text-black">
            <Eye className="w-5 h-5 text-black" />
          </div>
          <span className="text-xl sm:text-2xl font-bold tracking-wider text-white uppercase font-['DM_Sans']">
            SURGICAL<span className="text-[#0066FF]">.AI</span>
          </span>
        </div>

        {/* Desktop Pill Navigation - Perfectly Centered */}
        <nav className="hidden md:flex items-center justify-center bg-white/10 backdrop-blur-md border border-white/15 rounded-full p-1.5 shadow-lg mx-auto">
          {navItems.map((item) => {
            const isActive = activeTab === item;
            return (
              <button
                key={item}
                onClick={() => setActiveTab(item)}
                className={`px-4 py-1.5 rounded-full text-xs font-medium transition-all duration-200 cursor-pointer ${
                  isActive
                    ? 'bg-white text-black shadow-md font-semibold'
                    : 'text-white hover:text-white/80 hover:bg-white/5'
                }`}
              >
                {item}
              </button>
            );
          })}
        </nav>

        {/* Right Action - Right Aligned */}
        <div className="hidden md:flex items-center justify-end">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="bg-white/10 hover:bg-white/20 border border-white/20 text-white font-medium px-4 py-1.5 rounded-full text-xs backdrop-blur-md transition-all cursor-pointer flex items-center gap-2"
          >
            <span>Open menu</span>
          </button>
        </div>

        {/* Mobile Hamburger Toggle */}
        <div className="flex items-center justify-end md:hidden">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 text-white bg-white/10 rounded-full border border-white/20"
            aria-label="Toggle navigation"
          >
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile Navigation Dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden mt-4 bg-black/95 border border-white/20 rounded-2xl p-4 backdrop-blur-xl space-y-2 shadow-2xl">
          {navItems.map((item) => (
            <button
              key={item}
              onClick={() => {
                setActiveTab(item);
                setMobileMenuOpen(false);
              }}
              className={`w-full text-left px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                activeTab === item
                  ? 'bg-white text-black font-semibold'
                  : 'text-white hover:bg-white/10'
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      )}
    </header>
  );
}

