interface Props {
  reason: string;
  disabled: boolean;
  onAccept: () => void;
}

export default function DirectOffer({ reason, disabled, onAccept }: Props) {
  return (
    <div role="status" className="px-5 py-4 bg-note border-l-4 border-sun">
      <h3 className="text-lg font-semibold">{reason}</h3>
      <p className="mt-1 max-w-prose">
        You can still translate this text with the free allowance Hugging Face gives every visitor.
      </p>
      <ul className="mt-2 max-w-prose list-disc pl-5">
        <li>
          Your browser sends the text straight to our model on Hugging Face, which will see your IP
          address.
        </li>
        <li>Without an account you get about 2 minutes of GPU time a day, enough for short texts.</li>
        <li>Your requests wait behind signed-in users, so it can be slower.</li>
      </ul>
      <button onClick={onAccept} disabled={disabled} className="btn btn-primary mt-3 w-full sm:w-auto">
        Translate with my free allowance
      </button>
    </div>
  );
}
