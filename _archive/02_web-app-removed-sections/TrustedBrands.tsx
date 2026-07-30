import { Building2, Layers, HardHat, Compass, Landmark } from 'lucide-react';
import { motion } from 'motion/react';

export function TrustedBrands() {
  const logos = [
    {
      name: "CONSTRUCTOR",
      icon: Building2,
      subtext: "ENGINEERING"
    },
    {
      name: "CONDON",
      icon: Layers,
      subtext: "CONSTRUCTION"
    },
    {
      name: "Morrison",
      icon: HardHat,
      subtext: "Construction"
    },
    {
      name: "ARCHITECTURAL",
      icon: Compass,
      subtext: "SOLUTIONS"
    },
    {
      name: "VERTEX",
      icon: Landmark,
      subtext: "BUILD GROUP"
    }
  ];

  return (
    <section className="w-full max-w-7xl mx-auto mt-8 relative">
      {/* Container matching main banner frame */}
      <div className="w-full bg-transparent border-transparent rounded-3xl overflow-hidden relative shadow-2xl flex flex-col justify-between pt-16 sm:pt-20 pb-8 px-4 sm:px-8">
        {/* Subtle Radial Warm Ambient Glow behind text */}
        <div 
          className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[300px] rounded-full pointer-events-none opacity-25 blur-3xl"
          style={{
            background: 'radial-gradient(circle, rgba(220,70,40,0.4) 0%, rgba(120,40,30,0.2) 45%, rgba(0,0,0,0) 70%)'
          }}
        />

        {/* Content Area */}
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="relative z-10 text-center max-w-3xl mx-auto mb-16 sm:mb-20"
        >
          {/* Main Headline - Italic Serif Font as in reference */}
          <h2 className="text-4xl sm:text-6xl md:text-7xl font-serif italic text-white tracking-tight leading-[1.08] font-['Playfair_Display']">
            Proudly Trusted<br />
            by Leading Brands<br />
            Across Industries
            <sup className="text-red-600 font-sans not-italic text-2xl sm:text-4xl ml-1 font-bold">®</sup>
          </h2>

          {/* Subtext - DM Sans */}
          <p className="mt-6 text-sm sm:text-base text-white/80 font-['DM_Sans'] italic max-w-md mx-auto leading-relaxed">
            We've partnered with leading brands to deliver innovative and impactful solutions
          </p>
        </motion.div>

        {/* Horizontal Divider Line */}
        <div className="w-full border-t border-white/10 mb-8 sm:mb-10 relative z-10" />

        {/* Brand Logos Row */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
          className="relative z-10 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-6 sm:gap-8 items-center justify-items-center opacity-85 hover:opacity-100 transition-opacity"
        >
          {logos.map((brand, idx) => {
            const Icon = brand.icon;
            return (
              <div 
                key={idx} 
                className="flex items-center gap-2.5 text-white/80 hover:text-white transition-colors cursor-pointer group py-2 px-3"
              >
                <Icon className="w-6 h-6 text-white/90 group-hover:scale-110 transition-transform" />
                <div className="flex flex-col text-left">
                  <span className="text-xs sm:text-sm font-bold tracking-wider uppercase font-['DM_Sans'] text-white">
                    {brand.name}
                  </span>
                  <span className="text-[9px] tracking-widest text-white/50 uppercase font-['DM_Sans']">
                    {brand.subtext}
                  </span>
                </div>
              </div>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}
