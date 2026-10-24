import { useEffect, useRef } from "react";
import { CarFront, X } from "lucide-react";

export function Brand() {
  return (
    <div className="brand">
      <span className="brand-symbol">
        <CarFront size={23} />
      </span>
      <span>
        forecourt<span className="brand-period">.</span>
      </span>
    </div>
  );
}
export function Field({ label, ...props }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input {...props} />
    </label>
  );
}

export function Modal({ title, children, onClose, busy }) {
  const ref = useRef(null);
  useEffect(() => {
    const element = ref.current;
    element.showModal();
    return () => element.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby="modal-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="modal-head">
        <h2 id="modal-title">{title}</h2>
        <button aria-label="Close dialog" disabled={busy} onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
