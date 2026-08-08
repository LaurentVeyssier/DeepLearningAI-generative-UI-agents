
import { CopilotChat } from "@copilotkit/react-core/v2";
import { 
  useExampleDynamicSuggestions,
  useExampleFixedSuggestions
} from "@/hooks/use-example-suggestions";

export default function App() {
  useExampleDynamicSuggestions();
  useExampleFixedSuggestions();

  return <CopilotChat />;
}
