import { ArrowUpRight, Sparkles, Asterisk } from 'lucide-react';
import { motion } from 'motion/react';

export function StudioSection() {
  return (
    <section className="w-full max-w-7xl mx-auto mt-8 relative">
      {/* Black Container Box matching Section 1 and Section 2 */}
      <div className="w-full bg-transparent border-transparent rounded-3xl p-6 sm:p-10 md:p-12 relative overflow-hidden shadow-2xl text-white font-['DM_Sans']">
        
        {/* Header Content */}
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="max-w-4xl mx-auto text-center mb-12 sm:mb-16"
        >
          {/* Tag */}
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 border border-white/15 text-[11px] font-medium tracking-wider uppercase text-[#FF4500] mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-[#FF4500]" />
            About studio
          </div>

          {/* Main Headline with Star Accent */}
          <h2 className="text-3xl sm:text-5xl md:text-6xl font-medium tracking-tight text-white leading-[1.14] mb-4 font-['DM_Sans'] relative inline-block">
            <Asterisk className="inline-block w-7 h-7 sm:w-10 sm:h-10 text-[#FF4500] -mt-2 mr-2 animate-spin-slow" />
            Kinetic Studio – is an SMM agency of <span className="text-white font-semibold">bold creators</span> that delivers the power of social media with <span className="text-white/60">cutting-edge strategy</span>
          </h2>

          {/* Subtext */}
          <p className="text-xs sm:text-sm text-white/60 max-w-md mx-auto font-normal font-['DM_Sans'] mt-4 leading-relaxed">
            The Binderfox breezes through neon twilight with adjustable pancake logic orfox breezes through soon
          </p>
        </motion.div>

        {/* 4 Cards Row - Styled in Banner Glassmorphic Style with Staggered Heights */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 items-start pt-2 pb-6"
        >
          
          {/* Card 1 - Strategy (Tall) */}
          <div className="bg-gradient-to-b from-transparent to-[#0C1B3A]/90 border border-white/15 backdrop-blur-md rounded-2xl p-6 shadow-xl flex flex-col justify-between hover:border-white/30 transition-all duration-300 min-h-[340px] sm:min-h-[380px]">
            <div>
              {/* Top Pill Badge */}
              <div className="inline-block px-3.5 py-1 rounded-full bg-white/10 border border-white/20 text-xs font-medium text-white mb-8">
                Strategy
              </div>
            </div>

            <div className="mt-auto">
              <div className="w-2.5 h-2.5 rounded-full bg-[#FF3B30] mb-3" />
              <h3 className="text-lg sm:text-xl font-medium text-white mb-2 leading-tight">
                Bold strategies that shape identities
              </h3>
              <p className="text-xs sm:text-sm text-white/70 leading-relaxed mb-6">
                We craft concepts that define unique brands and strengthen their presence.
              </p>
              
              <button className="inline-flex items-center gap-2 text-sm font-semibold text-white hover:text-white/80 transition-all cursor-pointer bg-white/15 hover:bg-white/25 px-4 py-2 rounded-xl border border-white/20 shadow-md group">
                <ArrowUpRight size={18} className="group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                <span>Visit site</span>
              </button>
            </div>
          </div>

          {/* Card 2 - Growth (Slightly Staggered Down) */}
          <div className="bg-gradient-to-b from-transparent to-[#0C1B3A]/90 border border-white/15 backdrop-blur-md rounded-2xl p-6 shadow-xl flex flex-col justify-between hover:border-white/30 transition-all duration-300 min-h-[300px] sm:min-h-[320px] lg:mt-10">
            <div>
              {/* Top Pill Badge */}
              <div className="inline-block px-3.5 py-1 rounded-full bg-white/10 border border-white/20 text-xs font-medium text-white mb-8">
                Growth
              </div>
            </div>

            <div className="mt-auto">
              <div className="w-2.5 h-2.5 rounded-full bg-[#FF3B30] mb-3" />
              <h3 className="text-lg sm:text-xl font-medium text-white mb-2 leading-tight">
                Driving measurable growth through impact
              </h3>
              <p className="text-xs sm:text-sm text-white/70 leading-relaxed">
                Focused on reach, engagement, and real sales — not empty noise.
              </p>
            </div>
          </div>

          {/* Card 3 - Creative (Tall) */}
          <div className="bg-gradient-to-b from-transparent to-[#0C1B3A]/90 border border-white/15 backdrop-blur-md rounded-2xl p-6 shadow-xl flex flex-col justify-between hover:border-white/30 transition-all duration-300 min-h-[340px] sm:min-h-[380px]">
            <div>
              {/* Top Pill Badge */}
              <div className="inline-block px-3.5 py-1 rounded-full bg-white/10 border border-white/20 text-xs font-medium text-white mb-8">
                Creative
              </div>
            </div>

            <div className="mt-auto">
              <div className="w-2.5 h-2.5 rounded-full bg-[#FF3B30] mb-3" />
              <h3 className="text-lg sm:text-xl font-medium text-white mb-2 leading-tight">
                Creative processes with rapid delivery
              </h3>
              <p className="text-xs sm:text-sm text-white/70 leading-relaxed">
                Ideas turn into results fast, without losing quality or relevance.
              </p>
            </div>
          </div>

          {/* Card 4 - Powerful (Staggered Down) */}
          <div className="bg-gradient-to-b from-transparent to-[#0C1B3A]/90 border border-white/15 backdrop-blur-md rounded-2xl p-6 shadow-xl flex flex-col justify-between hover:border-white/30 transition-all duration-300 min-h-[300px] sm:min-h-[320px] lg:mt-14 relative">
            <div>
              {/* Top Pill Badge */}
              <div className="inline-block px-3.5 py-1 rounded-full bg-white/10 border border-white/20 text-xs font-medium text-white mb-8">
                Powerful
              </div>
            </div>

            <div className="mt-auto">
              <div className="w-2.5 h-2.5 rounded-full bg-[#FF3B30] mb-3" />
              <h3 className="text-lg sm:text-xl font-medium text-white mb-2 leading-tight">
                A dedicated team behind success
              </h3>
              <p className="text-xs sm:text-sm text-white/70 leading-relaxed">
                Our experts guide every step, from launch to scale.
              </p>
            </div>

            {/* Bottom Right Floating Icon Badge */}
            <div className="absolute bottom-4 right-4 w-10 h-10 rounded-2xl bg-white text-black flex items-center justify-center shadow-lg hover:scale-105 transition-transform">
              <Sparkles size={20} className="text-black" />
            </div>
          </div>

        </motion.div>
      </div>
    </section>
  );
}

