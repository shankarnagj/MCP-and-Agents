import { createContext, useContext, useReducer, type Dispatch, type ReactNode } from "react";
import { initialState, reducer, type Action, type State } from "./store";
import type { Me } from "../api/types";

const Ctx = createContext<{ state: State; dispatch: Dispatch<Action>; me: Me; ontology: any } | null>(null);

export function StoreProvider({ children, me, ontology }: { children: ReactNode; me: Me; ontology: any }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return <Ctx.Provider value={{ state, dispatch, me, ontology }}>{children}</Ctx.Provider>;
}

export function useStore() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useStore outside provider");
  return v;
}

export const can = (me: Me, perm: string) => me.permissions.includes(perm);
