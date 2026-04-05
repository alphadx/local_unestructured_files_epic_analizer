import { render, screen } from "@testing-library/react";
import Home from "./page";

describe("Home page", () => {
  it("renderiza la pestaña de grupos y la opción de modo de agrupación", () => {
    render(<Home />);

    expect(screen.getByRole("button", { name: /Análisis de Grupos/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/Modo de agrupación/i)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Strict \(solo directorio inmediato\)/i })).toBeInTheDocument();
  });
});
