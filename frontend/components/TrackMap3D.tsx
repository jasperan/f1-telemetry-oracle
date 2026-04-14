"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Line, Text } from "@react-three/drei";
import * as THREE from "three";
import clsx from "clsx";
import { useStore, CircuitPoint } from "@/lib/store";

/** Convert circuit points to THREE.Vector3 array. */
function toVec3Array(points: CircuitPoint[]): THREE.Vector3[] {
  return points.map((p) => new THREE.Vector3(p.x, p.z * 0.1, p.y));
}

/** Colorize track segment based on heatmap value. */
function getHeatmapColor(
  value: number,
  max: number,
  mode: "speed" | "brake" | "delta"
): string {
  const t = Math.min(1, Math.max(0, value / max));
  if (mode === "speed") {
    // Blue (slow) -> Cyan -> Green -> Yellow -> Red (fast), desaturated
    if (t < 0.25) return `hsl(220, 55%, ${28 + t * 140}%)`;
    if (t < 0.5) return `hsl(${220 - (t - 0.25) * 400}, 55%, 48%)`;
    if (t < 0.75) return `hsl(${120 - (t - 0.5) * 400}, 55%, 48%)`;
    return `hsl(${10}, 60%, 48%)`;
  }
  if (mode === "brake") {
    // Dark (no brake) -> Red (full brake), desaturated
    return `hsl(4, ${t * 65}%, ${20 + t * 28}%)`;
  }
  // delta: green (faster) to red (slower), desaturated
  if (value < 0) return `hsl(155, 55%, ${38 + Math.abs(value) * 15}%)`;
  return `hsl(4, 55%, ${38 + value * 15}%)`;
}

/** The 3D track line with optional heatmap coloring. */
function TrackLine({
  points,
  heatmapData,
  heatmapMode,
}: {
  points: THREE.Vector3[];
  heatmapData?: number[];
  heatmapMode: "speed" | "brake" | "delta" | null;
}) {
  if (points.length < 2) return null;

  if (!heatmapMode || !heatmapData) {
    return (
      <Line
        points={points}
        color="#3a3a44"
        lineWidth={3}
        dashed={false}
      />
    );
  }

  // Render colored segments
  const maxVal = Math.max(...heatmapData, 1);
  const segments: JSX.Element[] = [];

  for (let i = 0; i < points.length - 1; i++) {
    const val = heatmapData[i] ?? 0;
    const color = getHeatmapColor(val, maxVal, heatmapMode);
    segments.push(
      <Line
        key={i}
        points={[points[i], points[i + 1]]}
        color={color}
        lineWidth={4}
        dashed={false}
      />
    );
  }

  return <>{segments}</>;
}

/** Car position indicator -- glowing sphere on the track. */
function CarMarker({ position }: { position: THREE.Vector3 }) {
  const meshRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (meshRef.current) {
      // Subtle floating animation
      meshRef.current.position.y =
        position.y + Math.sin(state.clock.elapsedTime * 3) * 0.02;
    }
  });

  return (
    <mesh ref={meshRef} position={position}>
      <sphereGeometry args={[0.15, 16, 16]} />
      <meshStandardMaterial
        color="#4cb8d4"
        emissive="#4cb8d4"
        emissiveIntensity={0.7}
      />
      {/* Glow ring */}
      <mesh>
        <ringGeometry args={[0.2, 0.3, 32]} />
        <meshBasicMaterial
          color="#4cb8d4"
          transparent
          opacity={0.25}
          side={THREE.DoubleSide}
        />
      </mesh>
    </mesh>
  );
}

/** Sector boundary markers on the track. */
function SectorMarkers({ points }: { points: THREE.Vector3[] }) {
  if (points.length < 3) return null;

  // Approximate sector boundaries at 1/3 and 2/3 of track
  const s1Idx = Math.floor(points.length / 3);
  const s2Idx = Math.floor((points.length * 2) / 3);

  return (
    <>
      {[s1Idx, s2Idx].map((idx, i) => (
        <group key={i} position={points[idx]}>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <planeGeometry args={[0.05, 0.8]} />
            <meshBasicMaterial color="#d4a845" transparent opacity={0.6} />
          </mesh>
          <Text
            position={[0, 0.5, 0]}
            fontSize={0.2}
            color="#d4a845"
            anchorX="center"
            anchorY="bottom"
          >
            {`S${i + 1}`}
          </Text>
        </group>
      ))}
    </>
  );
}

/** Camera auto-framing to fit the track. */
function AutoFrame({ points }: { points: THREE.Vector3[] }) {
  const { camera } = useThree();
  const hasFramed = useRef(false);

  useEffect(() => {
    if (points.length < 2 || hasFramed.current) return;

    const box = new THREE.Box3();
    points.forEach((p) => box.expandByPoint(p));
    const center = new THREE.Vector3();
    box.getCenter(center);
    const size = new THREE.Vector3();
    box.getSize(size);

    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = (camera as THREE.PerspectiveCamera).fov;
    const dist = maxDim / (2 * Math.tan((fov * Math.PI) / 360));

    camera.position.set(center.x, dist * 1.2, center.z + dist * 0.5);
    camera.lookAt(center);
    camera.updateProjectionMatrix();
    hasFramed.current = true;
  }, [points, camera]);

  return null;
}

export default function TrackMap3D() {
  const {
    circuitGeometry,
    carPosition,
    heatmapOverlay,
    setCircuitGeometry,
    setHeatmapOverlay,
  } = useStore();

  const [loading, setLoading] = useState(false);
  const [heatmapData, setHeatmapData] = useState<number[]>([]);

  // Fetch circuit geometry
  useEffect(() => {
    const fetchCircuit = async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/circuits/current/geometry");
        if (res.ok) {
          const json = await res.json();
          setCircuitGeometry(
            json.points.map((p: [number, number, number]) => ({
              x: p[0],
              y: p[1],
              z: p[2] ?? 0,
            }))
          );
        } else {
          throw new Error("API unavailable");
        }
      } catch {
        // Use placeholder circuit (oval)
        const pts: CircuitPoint[] = [];
        for (let i = 0; i < 100; i++) {
          const angle = (i / 100) * Math.PI * 2;
          pts.push({
            x: Math.cos(angle) * 5 + Math.cos(angle * 3) * 0.5,
            y: Math.sin(angle) * 3 + Math.sin(angle * 5) * 0.3,
            z: 0,
          });
        }
        pts.push(pts[0]); // close the loop
        setCircuitGeometry(pts);
      }
      setLoading(false);
    };
    fetchCircuit();
  }, [setCircuitGeometry]);

  const trackPoints = useMemo(
    () => toVec3Array(circuitGeometry),
    [circuitGeometry]
  );

  const carPos = useMemo(
    () =>
      carPosition
        ? new THREE.Vector3(carPosition.x, carPosition.z * 0.1, carPosition.y)
        : null,
    [carPosition]
  );

  return (
    <article className="panel h-full flex flex-col">
      <div className="panel-header">
        <span className="panel-title">3D track map</span>
        <div className="flex gap-0.5">
          {(["speed", "brake", "delta", null] as const).map((mode) => (
            <button
              key={mode ?? "none"}
              onClick={() => setHeatmapOverlay(mode)}
              className={clsx(
                "chip-btn",
                heatmapOverlay === mode && "active"
              )}
            >
              {mode ?? "off"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {loading ? (
          <div className="h-full flex items-center justify-center">
            <div className="w-5 h-5 spinner" />
          </div>
        ) : (
          <Canvas
            camera={{ position: [0, 15, 10], fov: 50 }}
            style={{ background: "#0c0c0e" }}
          >
            <ambientLight intensity={0.35} />
            <directionalLight position={[10, 20, 10]} intensity={0.7} />
            <pointLight
              position={[0, 5, 0]}
              intensity={0.25}
              color="#4cb8d4"
            />

            {/* Ground plane */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.1, 0]}>
              <planeGeometry args={[50, 50]} />
              <meshStandardMaterial color="#0e0e11" />
            </mesh>

            {/* Track */}
            <TrackLine
              points={trackPoints}
              heatmapData={heatmapData.length > 0 ? heatmapData : undefined}
              heatmapMode={heatmapOverlay}
            />

            {/* Sector markers */}
            <SectorMarkers points={trackPoints} />

            {/* Car position */}
            {carPos && <CarMarker position={carPos} />}

            {/* Camera controls */}
            <OrbitControls
              enablePan
              enableZoom
              enableRotate
              minDistance={2}
              maxDistance={50}
              maxPolarAngle={Math.PI / 2.2}
            />

            {/* Auto-frame on load */}
            <AutoFrame points={trackPoints} />
          </Canvas>
        )}
      </div>
    </article>
  );
}
