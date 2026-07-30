import { useEffect, useRef } from 'react';

export const ScrollAnimation = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    const frameCount = 300;
    
    // Helper to get image path
    const currentFrame = (index: number) => (
      `/frames/ezgif-frame-${index.toString().padStart(3, '0')}.jpg`
    );

    const images: HTMLImageElement[] = [];
    
    let currentFrameIndex = 1;
    let targetFrameIndex = 1;

    // Adjust canvas to match device pixel ratio and screen size exactly
    const resizeCanvas = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      
      // If we already have images loaded, redraw the current frame
      const frameToDraw = Math.min(frameCount, Math.max(1, Math.round(currentFrameIndex)));
      const img = images[frameToDraw - 1];
      if (img && img.complete) {
        drawImageCover(img);
      }
    };

    // Function to draw an image covering the canvas (like object-fit: cover)
    const drawImageCover = (img: HTMLImageElement) => {
      context.clearRect(0, 0, canvas.width, canvas.height);
      
      const canvasRatio = canvas.width / canvas.height;
      const imgRatio = img.width / img.height;
      
      let drawWidth, drawHeight, offsetX, offsetY;

      if (imgRatio > canvasRatio) {
        // Image is wider than canvas
        drawHeight = canvas.height;
        drawWidth = img.width * (canvas.height / img.height);
        offsetX = (canvas.width - drawWidth) / 2;
        offsetY = 0;
      } else {
        // Image is taller than canvas
        drawWidth = canvas.width;
        drawHeight = img.height * (canvas.width / img.width);
        offsetX = 0;
        offsetY = (canvas.height - drawHeight) / 2;
      }
      
      // Ensure image smoothing is high for best quality scaling
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = 'high';
      
      context.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);
    };

    window.addEventListener('resize', resizeCanvas);
    resizeCanvas(); // Set initial size

    const preloadImages = () => {
      for (let i = 1; i <= frameCount; i++) {
        const img = new Image();
        img.src = currentFrame(i);
        img.onload = () => {
          // Draw first frame once loaded
          if (i === 1) {
            drawImageCover(img);
          }
        };
        images.push(img);
      }
    };
    
    preloadImages();

    // Calculate which frame to show based on scroll
    const handleScroll = () => {
      const scrollTop = document.documentElement.scrollTop;
      const maxScrollTop = document.documentElement.scrollHeight - window.innerHeight;
      
      // Prevent division by zero if page isn't scrollable
      const scrollFraction = maxScrollTop > 0 ? scrollTop / maxScrollTop : 0;
      
      // Calculate the target frame based on scroll position
      targetFrameIndex = Math.min(
        frameCount,
        Math.max(1, Math.ceil(scrollFraction * frameCount))
      );
    };

    window.addEventListener('scroll', handleScroll);

    let animationFrameId: number;

    const render = () => {
      // Smoothly interpolate current frame towards target frame
      currentFrameIndex += (targetFrameIndex - currentFrameIndex) * 0.08;
      
      const frameToDraw = Math.min(
        frameCount, 
        Math.max(1, Math.round(currentFrameIndex))
      );
      
      const img = images[frameToDraw - 1];
      if (img && img.complete) {
         drawImageCover(img);
      }
      
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      window.removeEventListener('scroll', handleScroll);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="fixed inset-0 z-[-1] flex items-center justify-center bg-black">
      <canvas ref={canvasRef} className="w-full h-full object-cover" />
    </div>
  );
};
